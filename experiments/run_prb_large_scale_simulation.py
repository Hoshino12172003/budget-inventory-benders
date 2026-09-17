from __future__ import annotations
import argparse, hashlib, json, os, platform, shutil, subprocess, sys
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter, sleep
from typing import Any
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from robust_inventory_reconfiguration.e1c_scaling import ScalingDimensions, build_renault_calibrated_instance
from robust_inventory_reconfiguration.instance import load_instance, save_instance
from robust_inventory_reconfiguration.nominal_baseline import baseline_feasibility, solve_canonical_nominal_baseline
from robust_inventory_reconfiguration.product_risk_budget_benders import solve_prb_benders
from robust_inventory_reconfiguration.pure_benders import solve_pure_benders
from robust_inventory_reconfiguration.standard_benders import solve_standard_benders

OUT = ROOT / "experiments/results/prb_large_scale_simulation_v1"
SOURCE_CASES=("210129","210202","210310","210323","210330","210428","210611","210628")
MAIN_SEEDS=tuple(range(20260921,20260931))
STRESS_SEEDS=tuple(range(20261001,20261006))
SCALES={
    "L10": ScalingDimensions("L10",25,24,12),
    "XL10": ScalingDimensions("XL10",30,30,14),
    "XXL10": ScalingDimensions("XXL10",36,36,16),
    "XXLP": ScalingDimensions("XXLP",40,40,16),
}
MAIN_SCALES=("L10","XL10","XXL10")
STRESS_SCALES=("XXLP",)
METHODS=("pure_benders","aggregate_benders_structured_oracle","prb_benders")
GAMMA=2; LAMBDA_R=0.05; REL_GAP=1e-6; CUT_TOL=1e-7; OBJ_TOL=1e-4; MAX_ITER=500
TIME_LIMIT=900.0; MIN_AVAIL=18.0; PROC_STOP=14.0; SYS_STOP=3.0; POLL=0.25

def rj(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def wj(p,v):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
def ch(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
def gitsha(): return subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
def hw():
    vm=psutil.virtual_memory()
    return {"platform":platform.platform(),"cpu":platform.processor(),"logical_cpu":os.cpu_count(),"ram_gib":vm.total/2**30}
def src_instances():
    return [load_instance(ROOT/f"data/formal_instances_v2/{c}.json") for c in SOURCE_CASES]
def tdir(scale,seed,task): return OUT/scale/str(seed)/task
def terminal(path):
    p=Path(path)/"result.json"
    return p.exists() and rj(p).get("terminal_record") is True

def ptreemem(pid):
    try:
        root=psutil.Process(pid); ps=[root,*root.children(recursive=True)]
    except psutil.Error: return 0.0
    total=0
    for p in ps:
        try:
            mi=p.memory_info(); total += max(int(mi.rss),int(getattr(mi,"private",0)))
        except psutil.Error: pass
    return total/2**30

def killtree(pid):
    try:
        root=psutil.Process(pid); ps=[*root.children(recursive=True),root]
    except psutil.Error: return
    for p in ps:
        try:p.terminate()
        except psutil.Error:pass
    _,alive=psutil.wait_procs(ps,timeout=3)
    for p in alive:
        try:p.kill()
        except psutil.Error:pass

def preflight():
    ss=[]
    for _ in range(3):
        a=psutil.virtual_memory().available/2**30; ss.append(a)
        if a<MIN_AVAIL: raise RuntimeError(f"RESOURCE_PREFLIGHT_BLOCKED {a:.3f} GiB < {MIN_AVAIL}")
        sleep(POLL)
    return ss

def run_monitored(scale,seed,task):
    target=tdir(scale,seed,task)
    if terminal(target): return rj(target/"result.json")
    if target.exists(): raise RuntimeError(f"NONTERMINAL_EXISTING_DIRECTORY {target}")
    part=target.with_name("."+target.name+".partial")
    if part.exists(): raise RuntimeError(f"STALE_PARTIAL_DIRECTORY {part}")
    samples=preflight(); part.mkdir(parents=True)
    cmd=[sys.executable,str(Path(__file__).resolve()),"--worker",task,"--scale",scale,"--seed",str(seed)]
    started=perf_counter(); peak=0.0; stop=None
    with (part/"stdout.log").open("w",encoding="utf-8") as so,(part/"stderr.log").open("w",encoding="utf-8") as se:
        pr=subprocess.Popen(cmd,cwd=part,stdout=so,stderr=se)
        while pr.poll() is None:
            m=ptreemem(pr.pid); peak=max(peak,m); avail=psutil.virtual_memory().available/2**30; elapsed=perf_counter()-started
            if m>=PROC_STOP: stop="RESOURCE_STOP"
            elif avail<=SYS_STOP: stop="RESOURCE_STOP"
            elif elapsed>=TIME_LIMIT: stop="TIME_LIMIT"
            if stop: killtree(pr.pid); break
            sleep(POLL)
        rc=pr.poll()
    elapsed=perf_counter()-started
    if stop or rc!=0:
        rec={"scale":scale,"seed":seed,"task":task,"status":stop or "ERROR","terminal_record":True,
             "development_only":True,"paper_final_observation":False,"preflight_available_memory_gib":samples,
             "peak_process_tree_memory_gib":peak,"monitor_wall_clock_seconds":elapsed,"worker_return_code":rc}
        wj(part/"result.json",rec)
    else:
        rec=rj(part/"result.json")
        rec.update({"terminal_record":True,"preflight_available_memory_gib":samples,
                    "peak_process_tree_memory_gib":peak,"monitor_wall_clock_seconds":elapsed})
        wj(part/"result.json",rec)
    target.parent.mkdir(parents=True,exist_ok=True); shutil.move(str(part),str(target))
    return rj(target/"result.json")

def prepare(scale,seed,target):
    st=perf_counter(); dims=SCALES[scale]
    primitive=build_renault_calibrated_instance(src_instances(),dims,seed)
    ph=ch(primitive.to_dict())
    can=solve_canonical_nominal_baseline(primitive)
    feas=baseline_feasibility(primitive,can.baseline)
    if not feas["capacity_compatible"] or not feas["ub_compatible"]: raise RuntimeError("X0_FEASIBILITY_FAIL")
    inst=replace(primitive,initial_inventory=can.baseline.x); save_instance(inst,target/"instance.json")
    b={"scale":scale,"seed":seed,"Gamma":GAMMA,"lambda_R":LAMBDA_R,"dimensions":asdict(dims),
       "primitive_hash":ph,"instance_hash":ch(inst.to_dict()),"x0_hash":ch(can.baseline.x),
       "B_ref":can.baseline.first_stage_spending,"canonical_rule":can.rule,"feasibility":feas,
       "primary_nominal_objective":can.primary_objective,
       "canonical_nominal_objective":can.canonical_objective,
       "primary_objective_delta":can.objective_delta,
       "objective_face_tolerance":can.objective_face_tolerance,
       "objective_face_validation_slack":can.objective_face_validation_slack,
       "primary_face_gate_tolerance":can.objective_face_tolerance + can.objective_face_validation_slack,
       "numerical_repair_used":can.numerical_repair_used,
       "repair_profile":can.repair_profile,
       "continuous_fix_tolerance":can.continuous_fix_tolerance,
       "maximum_constraint_violation":can.maximum_constraint_violation,
       "maximum_bound_violation":can.maximum_bound_violation,
       "maximum_integrality_violation":can.maximum_integrality_violation,
       "numerical_attempt_count":can.numerical_attempt_count,
       "nominal_solver_optimize_calls":can.solve_count,"git_commit":gitsha()}
    wj(target/"baseline.json",b)
    wj(target/"result.json",{"scale":scale,"seed":seed,"task":"PREPARE","status":"OPTIMAL",
       "exact_certification":True,"terminal_record":False,"core_runtime_seconds":perf_counter()-st,
       "development_only":True,"paper_final_observation":False,
       **{k:b[k] for k in ("instance_hash","x0_hash","B_ref","numerical_repair_used",
                           "repair_profile","primary_face_gate_tolerance")}})

def hist(s): return [asdict(x) for x in s.iterations]

def solve_method(scale,seed,method,target):
    prep=tdir(scale,seed,"PREPARE")
    if not terminal(prep): raise RuntimeError("PREPARE_NOT_COMPLETE")
    inst=load_instance(prep/"instance.json"); b=rj(prep/"baseline.json"); x0=inst.initial_inventory
    if x0 is None: raise RuntimeError("NO_X0")
    B=float(b["B_ref"])
    common={"scale":scale,"seed":seed,"task":method,"method":method,"Gamma":GAMMA,"beta":1.0,
            "lambda_R":LAMBDA_R,"B_ref":B,"dimensions":asdict(SCALES[scale]),"instance_hash":b["instance_hash"],
            "x0_hash":b["x0_hash"],"git_commit":gitsha(),"solver_version":".".join(map(str,__import__("gurobipy").gurobi.version())),
            "hardware":hw(),"development_only":True,"paper_final_observation":False}
    if method=="pure_benders":
        s=solve_pure_benders(inst,x0,B,GAMMA,LAMBDA_R,relative_gap_tolerance=REL_GAP,cut_tolerance=CUT_TOL,
            objective_certification_tolerance=OBJ_TOL,max_iterations=MAX_ITER,time_limit=TIME_LIMIT,log_file=target/"solver.log")
        cert=s.exact_certification_pass and s.cut_validity_pass
        rec={"status":s.status,"exact_certification":bool(cert),"objective":s.solution.objective,
             "final_lower_bound":s.final_lower_bound,"final_upper_bound":s.final_upper_bound,
             "final_relative_gap":s.final_relative_gap,"iterations":len(s.iterations),"cuts":s.aggregate_cut_count,
             "core_runtime_seconds":s.total_runtime,"master_runtime_seconds":s.master_runtime,
             "oracle_runtime_seconds":s.global_oracle_runtime,"certification_runtime_seconds":s.certification_runtime}
    elif method=="aggregate_benders_structured_oracle":
        s=solve_standard_benders(inst,x0,B,GAMMA,LAMBDA_R,relative_gap_tolerance=REL_GAP,cut_tolerance=CUT_TOL,
            objective_certification_tolerance=OBJ_TOL,max_iterations=MAX_ITER,time_limit=TIME_LIMIT,log_file=target/"solver.log")
        cert=s.exact_certification_pass and s.cut_validity_pass
        rec={"status":s.status,"exact_certification":bool(cert),"objective":s.solution.objective,
             "final_lower_bound":s.final_lower_bound,"final_upper_bound":s.final_upper_bound,
             "final_relative_gap":s.final_relative_gap,"iterations":len(s.iterations),"cuts":s.aggregate_cut_count,
             "core_runtime_seconds":s.total_runtime,"master_runtime_seconds":s.master_runtime,
             "oracle_runtime_seconds":s.oracle_runtime,"certification_runtime_seconds":s.certification_runtime}
    else:
        s=solve_prb_benders(inst,x0,B,GAMMA,LAMBDA_R,relative_gap_tolerance=REL_GAP,cut_tolerance=CUT_TOL,max_iterations=MAX_ITER)
        cert=s.exact_certification_pass and s.global_risk_budget_coupling_pass
        rec={"status":s.status,"exact_certification":bool(cert),"objective":s.solution.objective,
             "final_lower_bound":s.final_lower_bound,"final_upper_bound":s.final_upper_bound,
             "final_relative_gap":s.final_relative_gap,"iterations":len(s.iterations),"cuts":s.unique_product_cuts,
             "core_runtime_seconds":s.total_runtime,"master_runtime_seconds":s.master_runtime,
             "oracle_runtime_seconds":s.separation_runtime,"certification_runtime_seconds":s.certification_runtime}
    wj(target/"iteration_log.json",hist(s)); wj(target/"result.json",{**common,**rec,"terminal_record":False})

def worker(scale,seed,task):
    target=Path.cwd()
    if task=="PREPARE": prepare(scale,seed,target)
    else: solve_method(scale,seed,task,target)

def run_grid(stress=False):
    scales=STRESS_SCALES if stress else MAIN_SCALES; seeds=STRESS_SEEDS if stress else MAIN_SEEDS
    OUT.mkdir(parents=True,exist_ok=True)
    for scale in scales:
        for seed in seeds:
            print(f"[PREPARE] {scale} seed={seed}",flush=True)
            p=run_monitored(scale,seed,"PREPARE")
            if p.get("status")!="OPTIMAL": continue
            for m in METHODS:
                print(f"[RUN] {scale} seed={seed} method={m}",flush=True)
                r=run_monitored(scale,seed,m)
                print(f"[DONE] {r.get('status')} peak={r.get('peak_process_tree_memory_gib')}",flush=True)

def dry():
    donor_regions=sum(load_instance(ROOT/f"data/formal_instances_v2/{c}.json").num_regions for c in SOURCE_CASES)
    donor_depots=sum(load_instance(ROOT/f"data/formal_instances_v2/{c}.json").num_depots for c in SOURCE_CASES)
    data={"status":"DRY_RUN_PASS","optimization_calls":0,"main_scales":[asdict(SCALES[s]) for s in MAIN_SCALES],
          "main_seeds":list(MAIN_SEEDS),"stress_scales":[asdict(SCALES[s]) for s in STRESS_SCALES],
          "stress_seeds":list(STRESS_SEEDS),"methods":list(METHODS),"Gamma":GAMMA,"lambda_R":LAMBDA_R,
          "resource_gates":{"min_available_gib":MIN_AVAIL,"process_stop_gib":PROC_STOP,"system_stop_gib":SYS_STOP,
                            "timeout_seconds":TIME_LIMIT,"poll_seconds":POLL},
          "donor_pool":{"regions":donor_regions,"depots":donor_depots},"git_commit":gitsha()}
    OUT.mkdir(parents=True,exist_ok=True); wj(OUT/"dry_run.json",data); print(json.dumps(data,indent=2))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--run-main",action="store_true"); ap.add_argument("--run-stress",action="store_true")
    ap.add_argument("--worker",choices=("PREPARE",*METHODS)); ap.add_argument("--scale",choices=tuple(SCALES)); ap.add_argument("--seed",type=int)
    a=ap.parse_args()
    if a.worker:
        if a.scale is None or a.seed is None: ap.error("--worker requires --scale and --seed")
        worker(a.scale,a.seed,a.worker); return
    if sum(map(bool,(a.dry_run,a.run_main,a.run_stress)))!=1: ap.error("choose exactly one mode")
    if a.dry_run: dry()
    elif a.run_main: run_grid(False)
    else: run_grid(True)
if __name__=="__main__": main()
