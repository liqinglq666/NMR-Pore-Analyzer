# NMR-Pore-Analyzer

## 1. LF-NMR 弛豫模型

```math
\frac{1}{T_2}
=
\frac{1}{T_{2,\mathrm{bulk}}}
+\rho_2\frac{S}{V}
+\frac{D(\gamma G T_E)^2}{12}
```

```math
\frac{1}{T_2}\approx\rho_2\frac{S}{V}
```

```math
\frac{S}{V}=\frac{F_s}{r}
```

```math
\frac{1}{T_2}\approx\rho_2\frac{F_s}{r}
```

```math
r=\rho_2F_sT_2
```

---

## 2. T₂–孔半径转换

```math
T_2=4.2\ \mathrm{ms}
\quad\Longleftrightarrow\quad
r=100\ \mathrm{nm}
```

```math
k_r=\frac{100}{4.2}=23.8095238\ \mathrm{nm/ms}
```

```math
r\,[\mathrm{nm}]
=\frac{100}{4.2}T_2\,[\mathrm{ms}]
\approx23.81T_2
```

```math
T_2\,[\mathrm{ms}]
=0.042\,r\,[\mathrm{nm}]
```

---

## 3. 孔隙分级

### System A

```math
C_A(T_2)=
\begin{cases}
\mathrm{Gel}, & 0\le T_2<0.42 \\
\mathrm{Transition}, & 0.42\le T_2<4.2 \\
\mathrm{Capillary}, & 4.2\le T_2<41.7 \\
\mathrm{Air\text{-}voids}, & T_2\ge41.7
\end{cases}
```

```math
C_A(r)=
\begin{cases}
\mathrm{Gel}, & 0\le r<10\ \mathrm{nm} \\
\mathrm{Transition}, & 10\le r<100\ \mathrm{nm} \\
\mathrm{Capillary}, & 100\le r<992.86\ \mathrm{nm} \\
\mathrm{Air\text{-}voids}, & r\ge992.86\ \mathrm{nm}
\end{cases}
```

### System B

```math
C_B(T_2)=
\begin{cases}
\mathrm{Harmless}, & 0\le T_2<0.83 \\
\mathrm{Less\text{-}harmful}, & 0.83\le T_2<2.08 \\
\mathrm{Harmful}, & 2.08\le T_2<8.33 \\
\mathrm{More\text{-}harmful}, & T_2\ge8.33
\end{cases}
```

```math
C_B(r)=
\begin{cases}
\mathrm{Harmless}, & 0\le r<19.76\ \mathrm{nm} \\
\mathrm{Less\text{-}harmful}, & 19.76\le r<49.52\ \mathrm{nm} \\
\mathrm{Harmful}, & 49.52\le r<198.33\ \mathrm{nm} \\
\mathrm{More\text{-}harmful}, & r\ge198.33\ \mathrm{nm}
\end{cases}
```

---

## 4. 总信号与累积分布

```math
(T_{2,i},A_i),\qquad i=1,2,\ldots,N,\qquad A_i\ge0
```

```math
A_{\mathrm{tot}}=\sum_{i=1}^{N}A_i
```

```math
F_i
=\frac{\sum_{j=1}^{i}A_j}{\sum_{j=1}^{N}A_j}
```

```math
0\le F_i\le1,\qquad F_N=1
```

---

## 5. 孔隙比例积分

```math
I_k=[T_{2,k}^{L},T_{2,k}^{U})
```

### 5.1 Bin Summation

```math
i\in\mathcal I_k
\iff
T_{2,k}^{L}\le T_{2,i}<T_{2,k}^{U}
```

```math
S_k=\sum_{i\in\mathcal I_k}A_i
```

```math
\phi_k=\frac{S_k}{\sum_jS_j}
```

```math
\sum_k\phi_k=1
```

### 5.2 Log-domain Trapezoidal Integration

```math
x=\log_{10}T_2
```

```math
S_k^{(\log)}
=\int_{\log_{10}T_{2,k}^{L}}^{\log_{10}T_{2,k}^{U}}
A(T_2)\,d(\log_{10}T_2)
```

```math
S_k^{(\log)}
\approx
\sum_{i=1}^{m-1}
\frac{A_i+A_{i+1}}{2}
[\log_{10}T_{2,i+1}-\log_{10}T_{2,i}]
```

### 5.3 Linear Trapezoidal Integration

```math
S_k^{(\mathrm{lin})}
=\int_{T_{2,k}^{L}}^{T_{2,k}^{U}}A(T_2)\,dT_2
```

```math
S_k^{(\mathrm{lin})}
\approx
\sum_{i=1}^{m-1}
\frac{A_i+A_{i+1}}{2}
(T_{2,i+1}-T_{2,i})
```

```math
A(T_b)
=A_i
+\frac{A_{i+1}-A_i}{T_{2,i+1}-T_{2,i}}
(T_b-T_{2,i})
```

---

## 6. 主峰

```math
0\le T_2<10\ \mathrm{ms}
```

```math
A_{i_{\mathrm{pri}}}
=
\max_{0\le T_{2,i}<10}A_i
```

```math
T_{2,\mathrm{pri}}=T_{2,i_{\mathrm{pri}}}
```

```math
r_{\mathrm{pri}}=23.8095238\,T_{2,\mathrm{pri}}
```

```math
A_{\mathrm{pri}}=A_{i_{\mathrm{pri}}}
```

---

## 7. 次峰

```math
10<T_2\le1000\ \mathrm{ms}
```

严格局部极大值：

```math
A_i>A_{i-1},\qquad A_i>A_{i+1}
```

候选条件：

```math
i\in\mathcal P
\iff
10<T_{2,i}\le1000,
\quad A_i>A_{i-1},
\quad A_i>A_{i+1}
```

次峰：

```math
A_{i_{\mathrm{sec}}}
=
\max_{i\in\mathcal P}A_i
```

```math
T_{2,\mathrm{sec}}=T_{2,i_{\mathrm{sec}}}
```

```math
r_{\mathrm{sec}}=23.8095238\,T_{2,\mathrm{sec}}
```

若无候选次峰：

```math
\mathcal P=\varnothing
```

---

## 8. 峰间谷值

严格局部极小值：

```math
A_i<A_{i-1},\qquad A_i<A_{i+1}
```

候选条件：

```math
i\in\mathcal V
\iff
i_{\mathrm{pri}}<i<i_{\mathrm{sec}},
\quad A_i<A_{i-1},
\quad A_i<A_{i+1}
```

谷值：

```math
A_{i_v}=\min_{i\in\mathcal V}A_i
```

```math
T_{2,v}=T_{2,i_v}
```

若：

```math
\mathcal V=\varnothing
```

则在两峰之间选择最接近 10 ms 的采样点：

```math
i\in\mathcal I_b
\iff
i_{\mathrm{pri}}<i<i_{\mathrm{sec}}
```

```math
|T_{2,i_v}-10|
=
\min_{i\in\mathcal I_b}|T_{2,i}-10|
```

---

## 9. 主峰 / 次峰面积

主峰区域：

```math
i\in\mathcal I_{\mathrm{pri}}
\iff
T_{2,i}<T_{2,v}
```

```math
S_{\mathrm{pri}}
=\sum_{i\in\mathcal I_{\mathrm{pri}}}A_i
```

次峰区域：

```math
i\in\mathcal I_{\mathrm{sec}}
\iff
T_{2,i}\ge T_{2,v}
```

```math
S_{\mathrm{sec}}
=\sum_{i\in\mathcal I_{\mathrm{sec}}}A_i
```

```math
S_{\mathrm{tot}}
=S_{\mathrm{pri}}+S_{\mathrm{sec}}
=\sum_{i=1}^{N}A_i
```

```math
R_{\mathrm{pri}}
=\frac{S_{\mathrm{pri}}}{S_{\mathrm{tot}}}
```

```math
R_{\mathrm{sec}}
=\frac{S_{\mathrm{sec}}}{S_{\mathrm{tot}}}
```

```math
R_{\mathrm{pri}}+R_{\mathrm{sec}}=1
```

无次峰时：

```math
S_{\mathrm{pri}}=S_{\mathrm{tot}},\qquad R_{\mathrm{pri}}=1
```
