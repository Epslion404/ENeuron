"""在真实训练的 INT8 模型上评估三类精确无损跳过 + 与 2:4 有损剪枝对比。"""
import json, random
M=json.load(open('int8_model_qat.json',encoding='utf-8-sig'))
W0,b0,W1,b1=M['W0'],M['b0'],M['W1'],M['b1']
H,I,O=32,64,10
d=json.load(open('archive/legacy/digit8x8/digit8x8_fixture.json',encoding='utf-8-sig'))
S=d['samples']
random.seed(20260914)
idx=list(range(len(S))); random.shuffle(idx)
te=[S[i] for i in idx[1400:]]
print(f"模型: test acc {M['test_acc']:.4f}, train {M['train_acc']:.4f}")

# ---- 输入置换：使零像素聚集 ----
N=len(S); freq=[0]*64
for s in S:
    for i,p in enumerate(s['pixels']):
        if p: freq[i]+=1
PERM=sorted(range(64), key=lambda i: freq[i])
def zgr(order, ss):
    tot=z=0
    for s in ss:
        px=s['pixels']
        for g in range(16):
            tot+=1
            if not any(px[order[g*4+t]] for t in range(4)): z+=1
    return z/tot
random.seed(1); cur=PERM[:]; bestr=zgr(cur,S[:400]); best=cur[:]
for _ in range(4000):
    a,b=random.randrange(64),random.randrange(64)
    if a==b: continue
    cur[a],cur[b]=cur[b],cur[a]
    r=zgr(cur,S[:400])
    if r>bestr: bestr=r; best=cur[:]
    else: cur[a],cur[b]=cur[b],cur[a]
PERM=best
print(f"输入置换后全零激活组率: {zgr(PERM,te)*100:.1f}% (自然顺序 {zgr(list(range(64)),te)*100:.1f}%)")
# 重排权重以匹配置换
W0p=[[W0[j][PERM[i]] for i in range(I)] for j in range(H)]

def npu(px_p, skipmask0=None):
    """px_p 已按 PERM 重排。skipmask0[j][g]=True 表示跳过该组。"""
    h=[]
    for j in range(H):
        a=b0[j]
        for g in range(16):
            if skipmask0 and skipmask0[j][g]: continue
            a+=sum(W0p[j][g*4+t]*px_p[g*4+t] for t in range(4))
        h.append(max(0,min(127,a)))
    o=[b1[k]+sum(W1[k][j]*h[j] for j in range(H)) for k in range(O)]
    return h,o

def suffix(row):
    lo=[0]*17; hi=[0]*17
    for g in range(15,-1,-1):
        lo[g]=lo[g+1]+sum(min(0,row[g*4+t]*15) for t in range(4))
        hi[g]=hi[g+1]+sum(max(0,row[g*4+t]*15) for t in range(4))
    return lo,hi
SUF=[suffix(W0p[j]) for j in range(H)]
WNZ=[[any(W0p[j][g*4+t] for t in range(4)) for g in range(16)] for j in range(H)]

stats={k:0 for k in ['zero_act','zero_w','relu_early','exec']}
tot=0; correct_base=0; correct_exact=0
for s in te:
    px=[s['pixels'][PERM[i]] for i in range(I)]
    anz=[any(px[g*4:(g+1)*4]) for g in range(16)]   # 一拍 OR-reduce 得到，32 个单元共用
    _,o_base=npu(px)
    # 精确跳过版本
    h=[]
    for j in range(H):
        lo,hi=SUF[j]; a=b0[j]
        for g in range(16):
            tot+=1
            if a+hi[g]<=0 or a+lo[g]>=127:
                stats['relu_early']+=16-g; tot+=15-g; break
            if not anz[g]: stats['zero_act']+=1; continue
            if not WNZ[j][g]: stats['zero_w']+=1; continue
            stats['exec']+=1
            a+=sum(W0p[j][g*4+t]*px[g*4+t] for t in range(4))
        h.append(max(0,min(127,a)))
    o=[b1[k]+sum(W1[k][j]*h[j] for j in range(H)) for k in range(O)]
    assert o==o_base, "精确跳过改变了输出！"
    if max(range(O),key=lambda k:o_base[k])==s['label']: correct_base+=1
    if max(range(O),key=lambda k:o[k])==s['label']: correct_exact+=1
print()
print("=== L0 组处理分类（真实模型 + 397 测试样本）===")
for k in ['zero_act','zero_w','relu_early','exec']:
    print(f"  {k:12s} {stats[k]:7d}  {stats[k]/tot*100:5.1f}%")
skip=stats['zero_act']+stats['zero_w']+stats['relu_early']
print(f"  {'可精确跳过':12s} {skip:7d}  {skip/tot*100:5.1f}%   <- 输出逐 bit 不变")
print(f"\n输出一致性: {'PASS 逐样本 logits 完全相同' if correct_base==correct_exact else 'FAIL'}")
print(f"准确率 base {correct_base/len(te):.4f} / exact-skip {correct_exact/len(te):.4f}")
json.dump({'perm':PERM,'skip_rate':skip/tot,'stats':stats},open('exact_skip_result.json','w'))
