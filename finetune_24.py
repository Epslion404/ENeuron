"""核实：静态幅度 2:4 掩码 + 微调，能否恢复准确率？
这是 NVIDIA Ampere 2:4 的标准流程（稀疏化后必须微调）。
若成立，则 2:4 = 1.91x 压缩且零精度损失，我上一轮"剪枝不是压缩手段"的结论需要修正。
"""
import json, random, math
M=json.load(open('int8_model_qat.json',encoding='utf-8-sig'))
R=json.load(open('exact_skip_result.json',encoding='utf-8-sig'))
PERM=R['perm']; H,I,O=32,64,10
W0q,b0,W1q,b1=M['W0'],M['b0'],M['W1'],M['b1']
W0p=[[W0q[j][PERM[i]] for i in range(I)] for j in range(H)]

d=json.load(open('archive/legacy/digit8x8/digit8x8_fixture.json',encoding='utf-8-sig'))
S=d['samples']; random.seed(20260914)
idx=list(range(len(S))); random.shuffle(idx)
tr=[S[i] for i in idx[:1400]]; te=[S[i] for i in idx[1400:]]

def q8(v): return max(-128,min(127,int(round(v))))
def mag_mask(W,ng,nmeta,keep=2):
    m=[]
    for r in W:
        km=[False]*ng
        for me in range(nmeta):
            sc=sorted([(sum(abs(r[(me*4+i)*4+t]) for t in range(4)),i) for i in range(4)],
                      key=lambda x:(-x[0],x[1]))
            for _,i in sc[:keep]: km[me*4+i]=True
        m.append(km)
    return m
m0=mag_mask(W0p,16,4); m1=mag_mask(W1q,8,2)

def npu(px,W0f,W1f,bb0,bb1):
    h=[]
    for j in range(H):
        a=int(round(bb0[j]))
        for g in range(16):
            if not m0[j][g]: continue
            a+=sum(q8(W0f[j][g*4+t])*px[g*4+t] for t in range(4))
        h.append(max(0,min(127,a)))
    o=[]
    for k in range(O):
        a=int(round(bb1[k]))
        for g in range(8):
            if not m1[k][g]: continue
            a+=sum(q8(W1f[k][g*4+t])*h[g*4+t] for t in range(4))
        o.append(a)
    return h,o
def acc(W0f,W1f,bb0,bb1,ss):
    c=0
    for s in ss:
        px=[s['pixels'][PERM[i]] for i in range(I)]
        _,o=npu(px,W0f,W1f,bb0,bb1)
        if max(range(O),key=lambda k:o[k])==s['label']: c+=1
    return c/len(ss)

# 浮点影子权重，掩码固定，只训练存活权重
W0f=[[float(W0p[j][i]) for i in range(I)] for j in range(H)]
W1f=[[float(W1q[k][j]) for j in range(H)] for k in range(O)]
bb0=[float(v) for v in b0]; bb1=[float(v) for v in b1]
# 施加掩码
for j in range(H):
    for g in range(16):
        if not m0[j][g]:
            for t in range(4): W0f[j][g*4+t]=0.0
for k in range(O):
    for g in range(8):
        if not m1[k][g]:
            for t in range(4): W1f[k][g*4+t]=0.0

print(f"微调前 (静态2:4, 未微调): test {acc(W0f,W1f,bb0,bb1,te)*100:.2f}%")

TEMP=400.0
for ep in range(60):
    lr=0.0015*(0.5**(ep/25))
    random.shuffle(tr)
    for s in tr:
        px=[s['pixels'][PERM[i]] for i in range(I)]; y=s['label']
        raw=[];h=[]
        for j in range(H):
            a=bb0[j]
            for g in range(16):
                if m0[j][g]: a+=sum(W0f[j][g*4+t]*px[g*4+t] for t in range(4))
            raw.append(a); h.append(0.0 if a<0 else (127.0 if a>127 else a))
        o=[]
        for k in range(O):
            a=bb1[k]
            for g in range(8):
                if m1[k][g]: a+=sum(W1f[k][g*4+t]*h[g*4+t] for t in range(4))
            o.append(a)
        mx=max(o); ex=[math.exp((v-mx)/TEMP) for v in o]; Z=sum(ex); p=[e/Z for e in ex]
        go=[(p[k]-(1.0 if k==y else 0.0)) for k in range(O)]
        gh=[0.0]*H
        for j in range(H):
            if 0.0<raw[j]<127.0:
                gh[j]=sum(go[k]*W1f[k][j] for k in range(O) if m1[k][j//4])
        for k in range(O):
            gk=go[k]
            if gk:
                bb1[k]-=lr*gk*TEMP
                for g in range(8):
                    if not m1[k][g]: continue
                    for t in range(4):
                        j=g*4+t
                        if h[j]: W1f[k][j]-=lr*gk*h[j]
        for j in range(H):
            g_=gh[j]
            if g_:
                bb0[j]-=lr*g_*TEMP*0.02
                for g in range(16):
                    if not m0[j][g]: continue
                    for t in range(4):
                        i=g*4+t
                        if px[i]: W0f[j][i]-=lr*g_*px[i]*0.02
        for j in range(H):
            r=W0f[j]
            for i in range(I):
                if r[i]>127: r[i]=127.0
                elif r[i]<-128: r[i]=-128.0
        for k in range(O):
            r=W1f[k]
            for j in range(H):
                if r[j]>127: r[j]=127.0
                elif r[j]<-128: r[j]=-128.0
    if ep%15==14:
        print(f"  epoch {ep+1}: test {acc(W0f,W1f,bb0,bb1,te)*100:.2f}%")

fa=acc(W0f,W1f,bb0,bb1,te)
print(f"\n*** 静态2:4 + 微调 60 epoch: test {fa*100:.2f}%  (dense 基线 93.45%) ***")
# 微调后权重的位宽需求
w0v=[q8(v) for j in range(H) for g in range(16) if m0[j][g] for v in [W0f[j][g*4+t] for t in range(4)]]
w1v=[q8(v) for k in range(O) for g in range(8) if m1[k][g] for v in [W1f[k][g*4+t] for t in range(4)]]
print(f"微调后 L0 存活权重范围 [{min(w0v)},{max(w0v)}] -> 无损位宽 {max(1,math.ceil(math.log2(max(abs(min(w0v)),max(w0v)+1)))+1)} bit")
print(f"微调后 L1 存活权重范围 [{min(w1v)},{max(w1v)}] -> 无损位宽 {max(1,math.ceil(math.log2(max(abs(min(w1v)),max(w1v)+1)))+1)} bit")
json.dump({'W0':[[q8(v) for v in r] for r in W0f],'W1':[[q8(v) for v in r] for r in W1f],
           'b0':[int(round(v)) for v in bb0],'b1':[int(round(v)) for v in bb1],
           'mask0':m0,'mask1':m1,'test_acc':fa},open('int8_model_24_finetuned.json','w'))
print("saved int8_model_24_finetuned.json")
