"""量化感知训练 v2：更长训练 + 学习率退火 + 更好的初始化。
NPU 语义: hidden = clamp(b0 + sum(uint4_px * int8_w), 0, 127); logit = b1 + sum(h * int8_w)
"""
import json, random, math

d=json.load(open('archive/legacy/digit8x8/digit8x8_fixture.json',encoding='utf-8-sig'))
S=d['samples']
SPLIT_SEED = 20260914
TRAIN_POOL_COUNT = 1400
TRAIN_COUNT = 1200
VALIDATION_COUNT = TRAIN_POOL_COUNT - TRAIN_COUNT
HELDOUT_COUNT = len(S) - TRAIN_POOL_COUNT
split_rng = random.Random(SPLIT_SEED)
idx=list(range(len(S))); split_rng.shuffle(idx)
train_pool=[S[i] for i in idx[:TRAIN_POOL_COUNT]]
tr=train_pool[:TRAIN_COUNT]
val=train_pool[TRAIN_COUNT:]
te=[S[i] for i in idx[TRAIN_POOL_COUNT:]]

# 训练随机性与数据划分使用独立的确定性来源，避免评估集参与模型选择。
random.seed(SPLIT_SEED)
H,I,O=32,64,10

# 初始化：让 hidden 初始落在 0..127 中段。px 均值约 4.9, 64 个输入
# sum(w*px) ~ 64 * w * 4.9 -> 要 ~60, 则 w ~ 0.19
W0=[[random.gauss(0,0.6) for _ in range(I)] for _ in range(H)]
b0=[30.0+random.gauss(0,5) for _ in range(H)]
# hidden ~0..127, 32 个 -> sum(w1*h) ~ 32*w1*40; 要 logit 尺度 ~ 几千
W1=[[random.gauss(0,1.5) for _ in range(H)] for _ in range(O)]
b1=[0.0]*O

def q8(v): return max(-128,min(127,int(round(v))))

def fwd_soft(px):
    raw=[];h=[]
    for j in range(H):
        a=b0[j]+sum(W0[j][i]*px[i] for i in range(I))
        raw.append(a); h.append(0.0 if a<0 else (127.0 if a>127 else a))
    o=[b1[k]+sum(W1[k][j]*h[j] for j in range(H)) for k in range(O)]
    return raw,h,o

def npu_fwd_w(px,q0,qb0,q1,qb1):
    h=[max(0,min(127,qb0[j]+sum(q0[j][i]*px[i] for i in range(I)))) for j in range(H)]
    o=[qb1[k]+sum(q1[k][j]*h[j] for j in range(H)) for k in range(O)]
    return h,o

def quant():
    return ([[q8(v) for v in r] for r in W0],[int(round(v)) for v in b0],
            [[q8(v) for v in r] for r in W1],[int(round(v)) for v in b1])

def accuracy(dataset, q0, qb0, q1, qb1):
    return sum(
        1 for s in dataset
        if max(range(O), key=lambda k: npu_fwd_w(s['pixels'], q0, qb0, q1, qb1)[1][k]) == s['label']
    ) / len(dataset)

TEMP=400.0   # softmax 温度，匹配 logit 尺度
EPOCHS=150
best=(-1.0,None)
for ep in range(EPOCHS):
    lr=0.0015*(0.5**(ep/50))
    random.shuffle(tr)
    for s in tr:
        px=s['pixels']; y=s['label']
        raw,h,o=fwd_soft(px)
        m=max(o); ex=[math.exp((v-m)/TEMP) for v in o]; Z=sum(ex); p=[e/Z for e in ex]
        go=[(p[k]-(1.0 if k==y else 0.0)) for k in range(O)]
        gh=[0.0]*H
        for j in range(H):
            if 0.0<raw[j]<127.0:
                gh[j]=sum(go[k]*W1[k][j] for k in range(O))
        for k in range(O):
            gk=go[k]
            if gk:
                b1[k]-=lr*gk*TEMP
                for j in range(H):
                    if h[j]: W1[k][j]-=lr*gk*h[j]
        for j in range(H):
            g=gh[j]
            if g:
                b0[j]-=lr*g*TEMP*0.02
                for i in range(I):
                    if px[i]: W0[j][i]-=lr*g*px[i]*0.02
        for j in range(H):
            r=W0[j]
            for i in range(I):
                if r[i]>127: r[i]=127.0
                elif r[i]<-128: r[i]=-128.0
        for k in range(O):
            r=W1[k]
            for j in range(H):
                if r[j]>127: r[j]=127.0
                elif r[j]<-128: r[j]=-128.0
    if ep%15==14 or ep==EPOCHS-1:
        q0,qb0,q1,qb1=quant()
        acc=accuracy(val,q0,qb0,q1,qb1)
        print(f'  epoch {ep+1}: NPU 精确语义 validation acc {acc:.4f}')
        if acc>best[0]: best=(acc,(q0,qb0,q1,qb1))

valacc,(q0,qb0,q1,qb1)=best
tracc=accuracy(tr,q0,qb0,q1,qb1)
testacc=accuracy(te,q0,qb0,q1,qb1)
print(f'\n*** 最佳 NPU 精确语义: train {tracc:.4f} validation {valacc:.4f} test {testacc:.4f} ***')

nzg0=sum(1 for j in range(H) for g in range(16) if any(q0[j][g*4+t] for t in range(4)))
nzg1=sum(1 for k in range(O) for g in range(8) if any(q1[k][g*4+t] for t in range(4)))
print(f'非零组: L0 {nzg0}/512, L1 {nzg1}/80, 合计 {nzg0+nzg1}/592')
meta_ge3=0; meta_tot=0
for j in range(H):
    nz=[any(q0[j][g*4+t] for t in range(4)) for g in range(16)]
    for m in range(4):
        meta_tot+=1
        if sum(nz[m*4:(m+1)*4])>=3: meta_ge3+=1
for k in range(O):
    nz=[any(q1[k][g*4+t] for t in range(4)) for g in range(8)]
    for m in range(2):
        meta_tot+=1
        if sum(nz[m*4:(m+1)*4])>=3: meta_ge3+=1
print(f'非零组数>=3 的 meta: {meta_ge3}/{meta_tot} = {meta_ge3/meta_tot*100:.1f}%')
json.dump({
    'W0':q0,'b0':qb0,'W1':q1,'b1':qb1,
    'train_acc':tracc,
    'validation_acc':valacc,
    'test_acc':testacc,
    'model_version':'qat-v3-val200-temp400-150ep-seed20260914',
    'split_seed':SPLIT_SEED,
    'train_pool_count':TRAIN_POOL_COUNT,
    'train_count':TRAIN_COUNT,
    'validation_count':VALIDATION_COUNT,
    'heldout_count':HELDOUT_COUNT,
    'selection_protocol':'validation_accuracy_only_v1',
},open('int8_model_qat.json','w'),indent=2)
print('saved int8_model_qat.json')
