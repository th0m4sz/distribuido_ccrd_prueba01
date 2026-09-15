# Nota del modelo

## Ecuación usada

\[
\hat x_i=(x_i-P_{min,i})(P_{max,i}-x_i),\qquad
f_i=B-(b_i+2c_i x_i),
\]
\[
x_i[k+1]=x_i[k]+\alpha\hat x_i[k]
\sum_{j\in N_i}a_{ij}\hat x_j[k](f_i[k]-f_j[k]).
\]

Cada vecino recibe su propio estado, factor de capacidad y fitness. La arista es
bidireccional. La sustitución de ambos factores por factores de capacidad permite
que lo que aumenta en un extremo se reste del otro. La suma de potencias se conserva.
No se usa promedio global ni funciones de barrera.

Esta estructura aparece en RD_new00.pdf, sección 4, ecuación (3), página PDF 2.
Se adapta a mínimos distintos de cero. La base local está en las ecuaciones (8)
y (9) de notas_documento_base.pdf, sección 3, página PDF 5.

## Condición inicial aleatoria

En las notas, sección 5.2, página PDF 18 / impresa 226, se define

\[
\Delta_G=\{p_G\in\mathbb R_+^N:\sum_i p_{Gi}=P_d\}.
\]

Por tanto, «random initial condition pG(0) ∈ Delta_G» significa un reparto
aleatorio **cuya suma es la demanda**. No significa cualquier suma inicial.
Por ejemplo, [150,300,100,250] y [250,200,200,150] son repartos distintos de 800 kW.
En el problema completo se comprueban además los mínimos y máximos de cada generador.

La ecuación (38) conserva la suma inicial. No corrige por sí sola un desbalance.
El ejemplo de demanda variable por intervalos no especifica una corrección adicional
que permita atribuir esa propiedad a (38).

## Paso numérico y límites

`modelo.py` calcula un paso común conservador desde los parámetros de los
nodos y enlaces. No se reutiliza el paso del programa coordinado anterior.
La cota considera el tamaño de los intervalos, el máximo factor de capacidad,
las diferencias máximas de fitness y la curvatura de los costos. Se verifica el
respeto de límites y descenso del costo, sin recortar las potencias tras un paso.
`period_s` es el tiempo entre comunicaciones; no es el paso numérico `alpha`.

Cada nodo usa datos de la misma iteración de sus vecinos. Si faltan datos,
espera y después falla por timeout. No sustituye datos faltantes con datos antiguos.
La conservación se comprueba por iteración, no mezclando estados de rondas distintas.

## Alcance

La demanda debe ser fija y las potencias iniciales deben estar estrictamente
entre límites, sumando la demanda. Al saturarse un generador sus intercambios
se debilitan y puede bloquear caminos de optimización. Por eso no toda topología
conexa garantiza alcanzar el óptimo con este mix. El anillo de seis conserva
la demanda pero no alcanza el óptimo en el ejemplo; la estrella sí lo alcanza.

Los costos de los seis generadores proceden de Tabla 1 de las notas, página PDF 20.
La publicación germanobandoCCRD.pdf sirve de base para el factor de capacidad;
sus resultados para la arquitectura coordinada no garantizan automáticamente
la convergencia de esta adaptación local.

## Referencia interna

La sección 5.3 de las notas, página PDF 18, menciona la solución central mediante
condiciones KKT. `referencia.py` las utiliza fuera de los nodos para comprobar
el reparto, incluyendo el generador de costo lineal. No envía consignas a las placas.
Estas verificaciones se guardan en JSON y no generan gráficas adicionales.
