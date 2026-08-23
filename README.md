# NMR-Pore-Analyzer

## 1. LF-NMR 弛豫模型

$$
\frac{1}{T_2}
=
\frac{1}{T_{2,\mathrm{bulk}}}
+\rho_2\frac{S}{V}
+\frac{D(\gamma G T_E)^2}{12}
$$

短回波间隔、表面弛豫占主导时：

$$
\frac{1}{T_2}
\approx
\rho_2\frac{S}{V}
$$

若

$$
\frac{S}{V}=\frac{F_s}{r}
$$

则

$$
\frac{1}{T_2}
\approx
\rho_2\frac{F_s}{r}
$$

因此

$$
r=\rho_2F_sT_2
$$

其中：

$$
T_2:\ \text{横向弛豫时间},\qquad
\rho_2:\ \text{表面弛豫率},\qquad
S/V:\ \text{比表面积},\qquad
r:\ \text{等效孔半径}
$$

---

## 2. $T_2$–孔半径转换

程序采用标定点：

$$
T_2=4.2\ \mathrm{ms}
\quad\Longleftrightarrow\quad
r=100\ \mathrm{nm}
$$

因此

$$
k_r=\frac{100}{4.2}=23.8095238\ \mathrm{nm/ms}
$$

$$
\boxed{
r\,[\mathrm{nm}]
=\frac{100}{4.2}T_2\,[\mathrm{ms}]
\approx23.81T_2
}
$$

反算为

$$
\boxed{
T_2\,[\mathrm{ms}]
=0.042\,r\,[\mathrm{nm}]
}
$$

---

## 3. 孔隙分级

### System A

$$
C_A(T_2)=
\begin{cases}
\mathrm{Gel}, & 0\le T_2<0.42\\
\mathrm{Transition}, & 0.42\le T_2<4.2\\
\mathrm{Capillary}, & 4.2\le T_2<41.7\\
\mathrm{Air\!\text{-}\!voids}, & T_2\ge41.7
\end{cases}
$$

对应等效孔半径约为

$$
C_A(r)=
\begin{cases}
\mathrm{Gel}, & 0\le r<10\ \mathrm{nm}\\
\mathrm{Transition}, & 10\le r<100\ \mathrm{nm}\\
\mathrm{Capillary}, & 100\le r<992.86\ \mathrm{nm}\\
\mathrm{Air\!\text{-}\!voids}, & r\ge992.86\ \mathrm{nm}
\end{cases}
$$

### System B

$$
C_B(T_2)=
\begin{cases}
\mathrm{Harmless}, & 0\le T_2<0.83\\
\mathrm{Less\!\text{-}\!harmful}, & 0.83\le T_2<2.08\\
\mathrm{Harmful}, & 2.08\le T_2<8.33\\
\mathrm{More\!\text{-}\!harmful}, & T_2\ge8.33
\end{cases}
$$

对应等效孔半径约为

$$
C_B(r)=
\begin{cases}
\mathrm{Harmless}, & 0\le r<19.76\ \mathrm{nm}\\
\mathrm{Less\!\text{-}\!harmful}, & 19.76\le r<49.52\ \mathrm{nm}\\
\mathrm{Harmful}, & 49.52\le r<198.33\ \mathrm{nm}\\
\mathrm{More\!\text{-}\!harmful}, & r\ge198.33\ \mathrm{nm}
\end{cases}
$$

---

## 4. 总信号与累积分布

对离散反演谱

$$
\left\{T_{2,i},A_i\right\}_{i=1}^{N},
\qquad A_i\ge0
$$

总信号为

$$
A_{\mathrm{tot}}
=\sum_{i=1}^{N}A_i
$$

第 $i$ 个采样点的归一化累积分布为

$$
\boxed{
F_i
=\frac{\sum_{j=1}^{i}A_j}
{\sum_{j=1}^{N}A_j}
}
$$

且

$$
0\le F_i\le1,
\qquad
F_N=1
$$

---

## 5. 孔隙比例积分

设第 $k$ 个孔隙区间为

$$
I_k=[T_{2,k}^{L},T_{2,k}^{U})
$$

### 5.1 Bin Summation

$$
\boxed{
S_k
=\sum_{i:T_{2,i}\in I_k}A_i
}
$$

孔隙比例：

$$
\boxed{
\phi_k
=\frac{S_k}{\sum_jS_j}
}
$$

并满足

$$
\sum_k\phi_k=1
$$

### 5.2 Log-domain Trapezoidal Integration

令

$$
x=\log_{10}T_2
$$

则

$$
\boxed{
S_k^{(\log)}
=\int_{\log_{10}T_{2,k}^{L}}^{\log_{10}T_{2,k}^{U}}
A(T_2)\,d(\log_{10}T_2)
}
$$

离散梯形积分：

$$
S_k^{(\log)}
\approx
\sum_{i=1}^{m-1}
\frac{A_i+A_{i+1}}{2}
\left(
\log_{10}T_{2,i+1}-\log_{10}T_{2,i}
\right)
$$

### 5.3 Linear Trapezoidal Integration

$$
\boxed{
S_k^{(\mathrm{lin})}
=\int_{T_{2,k}^{L}}^{T_{2,k}^{U}}
A(T_2)\,dT_2
}
$$

离散形式：

$$
S_k^{(\mathrm{lin})}
\approx
\sum_{i=1}^{m-1}
\frac{A_i+A_{i+1}}{2}
\left(T_{2,i+1}-T_{2,i}\right)
$$

区间边界不落在原始采样点时，边界幅值由线性插值得到：

$$
A(T_b)
=
A_i+
\frac{A_{i+1}-A_i}{T_{2,i+1}-T_{2,i}}
\left(T_b-T_{2,i}\right)
$$

---

## 6. 主峰

主峰搜索区间：

$$
0\le T_2<10\ \mathrm{ms}
$$

主峰索引：

$$
\boxed{
i_{\mathrm{pri}}
=
\underset{i:\,0\le T_{2,i}<10}{\arg\max}\ A_i
}
$$

主峰位置：

$$
T_{2,\mathrm{pri}}=T_{2,i_{\mathrm{pri}}}
$$

$$
r_{\mathrm{pri}}
=23.8095238\,T_{2,\mathrm{pri}}
$$

主峰幅值：

$$
A_{\mathrm{pri}}=A_{i_{\mathrm{pri}}}
$$

---

## 7. 次峰

次峰搜索区间：

$$
10<T_2\le1000\ \mathrm{ms}
$$

严格局部极大值条件：

$$
A_i>A_{i-1}
\qquad\text{and}\qquad
A_i>A_{i+1}
$$

候选集合：

$$
\mathcal P
=
\left\{
i\mid
10<T_{2,i}\le1000,
\ A_i>A_{i-1},
\ A_i>A_{i+1}
\right\}
$$

次峰索引：

$$
\boxed{
i_{\mathrm{sec}}
=
\underset{i\in\mathcal P}{\arg\max}\ A_i
}
$$

若

$$
\mathcal P=\varnothing
$$

则不定义次峰。

---

## 8. 峰间谷值

若主峰与次峰同时存在，在两峰之间寻找严格局部极小值：

$$
A_i<A_{i-1}
\qquad\text{and}\qquad
A_i<A_{i+1}
$$

候选谷值集合：

$$
\mathcal V
=
\left\{
i\mid
i_{\mathrm{pri}}<i<i_{\mathrm{sec}},
\ A_i<A_{i-1},
\ A_i<A_{i+1}
\right\}
$$

谷值索引：

$$
\boxed{
i_v
=
\underset{i\in\mathcal V}{\arg\min}\ A_i
}
$$

$$
T_{2,v}=T_{2,i_v}
$$

若

$$
\mathcal V=\varnothing
$$

则使用最接近 $10\,\mathrm{ms}$ 的采样点：

$$
\boxed{
i_v
=
\underset{i}{\arg\min}
\left|T_{2,i}-10\right|
}
$$

---

## 9. 主峰/次峰面积

以谷值 $T_{2,v}$ 为分界：

$$
\boxed{
S_{\mathrm{pri}}
=\sum_{i:T_{2,i}<T_{2,v}}A_i
}
$$

$$
\boxed{
S_{\mathrm{sec}}
=\sum_{i:T_{2,i}\ge T_{2,v}}A_i
}
$$

$$
S_{\mathrm{tot}}
=S_{\mathrm{pri}}+S_{\mathrm{sec}}
=\sum_{i=1}^{N}A_i
$$

面积占比：

$$
\boxed{
R_{\mathrm{pri}}
=\frac{S_{\mathrm{pri}}}{S_{\mathrm{tot}}}
}
$$

$$
\boxed{
R_{\mathrm{sec}}
=\frac{S_{\mathrm{sec}}}{S_{\mathrm{tot}}}
}
$$

$$
R_{\mathrm{pri}}+R_{\mathrm{sec}}=1
$$

无次峰时：

$$
S_{\mathrm{pri}}=S_{\mathrm{tot}},
\qquad
R_{\mathrm{pri}}=1
$$
