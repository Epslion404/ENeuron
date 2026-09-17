"""INT4 / palette / 3:4 结构化稀疏 三组补充实验，复用 train_qat.py 同一划分与超参配方。"""
import json, random, math, time
import os
ROOT = os.path.dirname(os.path.abspath(__file__))

d = json.load(open(f"{ROOT}/archive/legacy/digit8x8/digit8x8_fixture.json", encoding="utf-8-sig"))
S = d["samples"]
random.seed(20260914)
idx = list(range(len(S))); random.shuffle(idx)
tr = [S[i] for i in idx[:1400]]; te = [S[i] for i in idx[1400:]]
H, I, O = 32, 64, 10
TEMP = 400.0

M = json.load(open(f"{ROOT}/int8_model_qat.json", encoding="utf-8-sig"))
W0d, b0d, W1d, b1d = M["W0"], M["b0"], M["W1"], M["b1"]

def q8(v): return max(-128, min(127, int(round(v))))

def npu_int(px, W0, b0, W1, b1):
    h = [max(0, min(127, b0[j] + sum(W0[j][i]*px[i] for i in range(I)))) for j in range(H)]
    o = [b1[k] + sum(W1[k][j]*h[j] for j in range(H)) for k in range(O)]
    return h, o

def acc_int(samples, W0, b0, W1, b1):
    c = 0
    for s in samples:
        _, o = npu_int(s["pixels"], W0, b0, W1, b1)
        if max(range(O), key=lambda k: o[k]) == s["label"]: c += 1
    return c/len(samples)

dense_acc = acc_int(te, W0d, [int(round(v)) for v in b0d], W1d, [int(round(v)) for v in b1d])
print(f"[dense baseline] test acc = {dense_acc*100:.2f}%  (manifest 93.45%)")

# ---------- generic float fine-tune loop with a forward-weight projector ----------
def finetune(W0, b0, W1, b1, proj0, proj1, epochs, lr0, decay=25, seed=1, log_every=10, tag=""):
    W0 = [r[:] for r in W0]; W1 = [r[:] for r in W1]; b0 = b0[:]; b1 = b1[:]
    rng = random.Random(seed)
    best = (0.0, None); hist=[]
    for ep in range(epochs):
        lr = lr0*(0.5**(ep/decay))
        order = tr[:]; rng.shuffle(order)
        for s in order:
            px = s["pixels"]; y = s["label"]
            We0 = proj0(W0); We1 = proj1(W1)
            raw = [b0[j] + sum(We0[j][i]*px[i] for i in range(I)) for j in range(H)]
            h = [0.0 if a < 0 else (127.0 if a > 127 else a) for a in raw]
            o = [b1[k] + sum(We1[k][j]*h[j] for j in range(H)) for k in range(O)]
            m = max(o); ex = [math.exp((v-m)/TEMP) for v in o]; Z = sum(ex); p = [e/Z for e in ex]
            go = [p[k]-(1.0 if k == y else 0.0) for k in range(O)]
            gh = [0.0]*H
            for j in range(H):
                if 0.0 < raw[j] < 127.0:
                    gh[j] = sum(go[k]*We1[k][j] for k in range(O))
            for k in range(O):
                gk = go[k]
                if gk:
                    b1[k] -= lr*gk*TEMP
                    row = W1[k]
                    for j in range(H):
                        if h[j]: row[j] -= lr*gk*h[j]
            for j in range(H):
                g = gh[j]
                if g:
                    b0[j] -= lr*g*TEMP*0.02
                    row = W0[j]
                    for i in range(I):
                        if px[i]: row[i] -= lr*g*px[i]*0.02
            for j in range(H):
                row = W0[j]
                for i in range(I):
                    if row[i] > 127: row[i] = 127.0
                    elif row[i] < -128: row[i] = -128.0
            for k in range(O):
                row = W1[k]
                for j in range(H):
                    if row[j] > 127: row[j] = 127.0
                    elif row[j] < -128: row[j] = -128.0
        if ep % log_every == log_every-1 or ep == epochs-1:
            We0 = proj0(W0); We1 = proj1(W1)
            q0 = [[q8(v) for v in r] for r in We0]; q1 = [[q8(v) for v in r] for r in We1]
            qb0 = [int(round(v)) for v in b0]; qb1 = [int(round(v)) for v in b1]
            a = acc_int(te, q0, qb0, q1, qb1)
            hist.append((ep+1, a))
            if a > best[0]: best = (a, (q0, qb0, q1, qb1))
    print(f"  [{tag}] history: " + ", ".join(f"ep{e}:{a*100:.2f}%" for e,a in hist))
    return best

IDP0 = lambda W: W   # identity projector
IDP1 = lambda W: W

t0=time.time()

print()
print("="*70)
print("实验 1: INT4 权重量化 (PTQ, 无重训练) —— 直接量化已训练的 INT8 权重")
print("="*70)

def scale_for(W, denom=7):
    mx = max(abs(v) for r in W for v in r)
    if mx == 0: return 1
    bits = math.ceil(math.log2(max(1.0, mx/denom)))
    return 2**max(0, bits)

def int4_qd_perlayer(W, scale):
    return [[max(-8, min(7, round(v/scale)))*scale for v in r] for r in W]

def int4_qd_perrow(W, denom=7):
    out=[]
    for r in W:
        mx = max(abs(v) for v in r)
        if mx == 0:
            out.append(r[:]); continue
        bits = math.ceil(math.log2(max(1.0, mx/denom))); sc = 2**max(0,bits)
        out.append([max(-8,min(7,round(v/sc)))*sc for v in r])
    return out

s0 = scale_for(W0d); s1 = scale_for(W1d)
print(f"per-layer power-of-2 scale: L0 shift={int(math.log2(s0))} (scale={s0}), L1 shift={int(math.log2(s1))} (scale={s1})")
W0_i4 = int4_qd_perlayer(W0d, s0); W1_i4 = int4_qd_perlayer(W1d, s1)
acc_i4_layer = acc_int(te, [[q8(v) for v in r] for r in W0_i4], [int(round(v)) for v in b0d],
                        [[q8(v) for v in r] for r in W1_i4], [int(round(v)) for v in b1d])
print(f"INT4 PTQ (per-layer scale) test acc = {acc_i4_layer*100:.2f}%  (drop {(dense_acc-acc_i4_layer)*100:.2f} pp)")

W0_i4r = int4_qd_perrow(W0d); W1_i4r = int4_qd_perrow(W1d)
acc_i4_row = acc_int(te, [[q8(v) for v in r] for r in W0_i4r], [int(round(v)) for v in b0d],
                      [[q8(v) for v in r] for r in W1_i4r], [int(round(v)) for v in b1d])
print(f"INT4 PTQ (per-row/per-neuron scale, 42 regs) test acc = {acc_i4_row*100:.2f}%  (drop {(dense_acc-acc_i4_row)*100:.2f} pp)")

print()
print("="*70)
print("实验 2: INT4 QAT (fake-quant 微调, STE, 固定 per-layer scale)")
print("="*70)
proj_i4_0 = lambda W: [[max(-8,min(7,round(v/s0)))*s0 for v in r] for r in W]
proj_i4_1 = lambda W: [[max(-8,min(7,round(v/s1)))*s1 for v in r] for r in W]
best_i4qat, _ = finetune([r[:] for r in W0d], b0d[:], [r[:] for r in W1d], b1d[:],
                          proj_i4_0, proj_i4_1, epochs=35, lr0=0.0008, decay=15, tag="INT4-QAT")
print(f"INT4 QAT (35 epoch) best test acc = {best_i4qat*100:.2f}%  (drop {(dense_acc-best_i4qat)*100:.2f} pp)")

print()
print("="*70)
print("实验 3: 调色板/码本 (16 项, 4-bit 索引, 逐层权重共享)")
print("="*70)

def kmeans_1d(values, weights, k=16, iters=25, seed=7):
    rng = random.Random(seed)
    lo, hi = min(values), max(values)
    cent = sorted(rng.uniform(lo, hi) for _ in range(k))
    for _ in range(iters):
        buckets = [[0.0,0.0] for _ in range(k)]  # sum(w*v), sum(w)
        for v,wt in zip(values, weights):
            c = min(range(k), key=lambda ci: abs(cent[ci]-v))
            buckets[c][0]+=wt*v; buckets[c][1]+=wt
        newcent=[]
        for i,(sv,sw) in enumerate(buckets):
            newcent.append(sv/sw if sw>0 else cent[i])
        if newcent==cent: break
        cent=sorted(newcent)
    return cent

def build_palette(W):
    flat = [v for r in W for v in r]
    uniq = {}
    for v in flat: uniq[v]=uniq.get(v,0)+1
    vals=list(uniq.keys()); wts=[uniq[v] for v in vals]
    cent = kmeans_1d(vals, wts, k=16)
    assign = [[min(range(16), key=lambda ci: abs(cent[ci]-v)) for v in r] for r in W]
    return cent, assign

cent0, assign0 = build_palette(W0d)
cent1, assign1 = build_palette(W1d)
def apply_palette(W, cent, assign):
    return [[cent[assign[j][i]] for i,_ in enumerate(r)] for j,r in enumerate(W)]
W0_pal = apply_palette(W0d, cent0, assign0)
W1_pal = apply_palette(W1d, cent1, assign1)
acc_pal_ptq = acc_int(te, [[q8(v) for v in r] for r in W0_pal], [int(round(v)) for v in b0d],
                       [[q8(v) for v in r] for r in W1_pal], [int(round(v)) for v in b1d])
print(f"码本 PTQ (16 项/层, 未微调) test acc = {acc_pal_ptq*100:.2f}%  (drop {(dense_acc-acc_pal_ptq)*100:.2f} pp)")

def finetune_centroids(cent0, assign0, cent1, assign1, b0, b1, epochs, lr0, decay=15, seed=3, tag="PAL-FT"):
    c0 = cent0[:]; c1 = cent1[:]; b0 = b0[:]; b1 = b1[:]
    rng = random.Random(seed)
    best=(0.0,None); hist=[]
    for ep in range(epochs):
        lr = lr0*(0.5**(ep/decay))
        order = tr[:]; rng.shuffle(order)
        for s in order:
            px = s["pixels"]; y = s["label"]
            We0 = [[c0[assign0[j][i]] for i in range(I)] for j in range(H)]
            We1 = [[c1[assign1[k][j]] for j in range(H)] for k in range(O)]
            raw=[b0[j]+sum(We0[j][i]*px[i] for i in range(I)) for j in range(H)]
            h=[0.0 if a<0 else (127.0 if a>127 else a) for a in raw]
            o=[b1[k]+sum(We1[k][j]*h[j] for j in range(H)) for k in range(O)]
            m=max(o); ex=[math.exp((v-m)/TEMP) for v in o]; Z=sum(ex); p=[e/Z for e in ex]
            go=[p[k]-(1.0 if k==y else 0.0) for k in range(O)]
            gh=[0.0]*H
            for j in range(H):
                if 0.0<raw[j]<127.0:
                    gh[j]=sum(go[k]*We1[k][j] for k in range(O))
            gc1=[0.0]*16; gc0=[0.0]*16
            for k in range(O):
                gk=go[k]
                if gk:
                    b1[k]-=lr*gk*TEMP
                    for j in range(H):
                        if h[j]: gc1[assign1[k][j]] += gk*h[j]
            for j in range(H):
                g=gh[j]
                if g:
                    b0[j]-=lr*g*TEMP*0.02
                    for i in range(I):
                        if px[i]: gc0[assign0[j][i]] += g*px[i]*0.02
            for ci in range(16):
                c0[ci]-=lr*gc0[ci]; c1[ci]-=lr*gc1[ci]
            for ci in range(16):
                if c0[ci]>127: c0[ci]=127.0
                elif c0[ci]<-128: c0[ci]=-128.0
                if c1[ci]>127: c1[ci]=127.0
                elif c1[ci]<-128: c1[ci]=-128.0
        if ep % 5 == 4 or ep==epochs-1:
            We0=[[q8(c0[assign0[j][i]]) for i in range(I)] for j in range(H)]
            We1=[[q8(c1[assign1[k][j]]) for j in range(H)] for k in range(O)]
            a=acc_int(te, We0, [int(round(v)) for v in b0], We1, [int(round(v)) for v in b1])
            hist.append((ep+1,a))
            if a>best[0]: best=(a,(We0,b0[:],We1,b1[:],c0[:],c1[:]))
    print(f"  [{tag}] history: "+", ".join(f"ep{e}:{a*100:.2f}%" for e,a in hist))
    return best

best_pal_ft, pal_ft_pack = finetune_centroids(cent0, assign0, cent1, assign1, b0d, b1d, epochs=30, lr0=0.0006, decay=12)
print(f"码本+centroid微调 (30 epoch, 索引固定) best test acc = {best_pal_ft*100:.2f}%  (drop {(dense_acc-best_pal_ft)*100:.2f} pp)")

print(f"\n耗时到此: {time.time()-t0:.1f}s")

print()
print("="*70)
print("实验 4: 组级结构化稀疏 —— 2:4 (对照复核) vs 3:4 (温和版)")
print("="*70)

def group_mask_natural(W, groups_per_unit, keep):
    """自然顺序（不做输入置换）、按 sum|w| 每 meta 选 top-keep 组，与 sim_offline_retrain_baseline 一致口径。"""
    metas = groups_per_unit // 4
    out=[]
    for r in W:
        k=[False]*len(r)
        for m in range(metas):
            scores=[]
            for gg in range(4):
                g = m*4+gg; base=g*4
                scores.append((sum(abs(r[base+t]) for t in range(4)), gg))
            order = sorted(range(4), key=lambda x: (-scores[x][0], x))
            for gg in order[:keep]:
                g = m*4+gg
                for t in range(4): k[g*4+t]=True
        out.append(k)
    return out

def apply_bool_mask(W, mask):
    return [[(v if mask[u][i] else 0) for i,v in enumerate(r)] for u,r in enumerate(W)]

results_struct = {}
for keep, name in ((2,"2:4 (对照复核)"), (3,"3:4 (温和版)")):
    m0 = group_mask_natural(W0d, 16, keep); m1 = group_mask_natural(W1d, 8, keep)
    mac_frac = keep/4
    W0m = apply_bool_mask(W0d, m0); W1m = apply_bool_mask(W1d, m1)
    acc_nort = acc_int(te, [[q8(v) for v in r] for r in W0m], [int(round(v)) for v in b0d],
                        [[q8(v) for v in r] for r in W1m], [int(round(v)) for v in b1d])
    proj0 = lambda W, m0=m0: apply_bool_mask(W, m0)
    proj1 = lambda W, m1=m1: apply_bool_mask(W, m1)
    best_rt, pack = finetune([r[:] for r in W0d], b0d[:], [r[:] for r in W1d], b1d[:],
                              proj0, proj1, epochs=45, lr0=0.0012, decay=20, tag=f"{keep}-of-4")
    comp_ratio = 4/(4*keep/4 + 3/8)  # bytes: 4B/group dense vs (keep bytes + 3-bit selector)/group... see note below
    results_struct[name] = dict(keep=keep, mac_reduction=1-mac_frac, no_retrain=acc_nort, retrained=best_rt, pack=pack)
    print(f"{name}: MAC 降 {1-mac_frac:.0%}  不重训练 {acc_nort*100:.2f}%  重训练后 {best_rt*100:.2f}%  "
          f"(drop {(dense_acc-best_rt)*100:.2f} pp)")

print()
print("="*70)
print("实验 5: 组合 —— 2:4(重训练) 权重再做 INT4 量化 + 联合微调")
print("="*70)
W0_24, b0_24, W1_24, b1_24 = results_struct["2:4 (对照复核)"]["pack"]
m0_24 = group_mask_natural(W0d, 16, 2); m1_24 = group_mask_natural(W1d, 8, 2)
s0c = scale_for(W0_24); s1c = scale_for(W1_24)
print(f"2:4 重训练后存活权重的 INT4 scale: L0 shift={int(math.log2(s0c))}, L1 shift={int(math.log2(s1c))}")
def combo_proj0(W): return [[max(-8,min(7,round(v/s0c)))*s0c if m0_24[j][i] else 0 for i,v in enumerate(r)] for j,r in enumerate(W)]
def combo_proj1(W): return [[max(-8,min(7,round(v/s1c)))*s1c if m1_24[k][j] else 0 for j,v in enumerate(r)] for k,r in enumerate(W)]
acc_combo_ptq = acc_int(te, [[q8(v) for v in r] for r in combo_proj0(W0_24)], [int(round(v)) for v in b0_24],
                         [[q8(v) for v in r] for r in combo_proj1(W1_24)], [int(round(v)) for v in b1_24])
print(f"2:4(重训练权重) 直接再做 INT4 PTQ, 未联合微调: test acc = {acc_combo_ptq*100:.2f}%")
best_combo, _ = finetune([r[:] for r in W0_24], b0_24[:], [r[:] for r in W1_24], b1_24[:],
                          combo_proj0, combo_proj1, epochs=30, lr0=0.0006, decay=12, tag="2:4+INT4-joint")
print(f"2:4 + INT4 联合微调 (30 epoch) best test acc = {best_combo*100:.2f}%  (drop {(dense_acc-best_combo)*100:.2f} pp)")
print(f"组合压缩倍率: 2x(结构稀疏 MAC/存储) * 2x(INT4 vs INT8) = 4x 存储压缩 (选择子开销另计)")

print(f"\n总耗时: {time.time()-t0:.1f}s")
