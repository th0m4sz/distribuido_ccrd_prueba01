# Nota del modelo

## Ecuación usada

$$
\hat x_i=(x_i-P_{min,i})(P_{max,i}-x_i),\qquad
f_i=B-(b_i+2c_i x_i).
$$

La ecuación (3) de `RD_new00.pdf` es

$$
x_i[k+1]=x_i[k]+\alpha\hat x_i[k]
\left(
f_i[k]\sum_{j\in\mathcal N_i}\hat x_j[k]
-\sum_{j\in\mathcal N_i}\hat x_j[k]f_j[k]
\right).
$$

Al introducir la primera suma dentro de una sola sumatoria,

$$
f_i[k]\sum_{j\in\mathcal N_i}\hat x_j[k]
-\sum_{j\in\mathcal N_i}\hat x_j[k]f_j[k]
=\sum_{j\in\mathcal N_i}\hat x_j[k](f_i[k]-f_j[k]),
$$

se obtiene la forma equivalente utilizada por el código:

$$
x_i[k+1]=x_i[k]+\alpha\hat x_i[k]
\sum_{j\in\mathcal N_i}a_{ij}\hat x_j[k](f_i[k]-f_j[k]).
$$

El factor $a_{ij}$ permite asignar un peso a cada conexión. En las configuraciones
actuales todas las conexiones tienen $a_{ij}=1$, por lo que la implementación
coincide exactamente con la ecuación del borrador.

Cada vecino recibe su propio estado, factor de capacidad y fitness. La arista es
bidireccional. La sustitución de ambos factores por factores de capacidad permite
que lo que aumenta en un extremo se reste del otro. La suma de potencias se conserva.
No se usa promedio global ni funciones de barrera.

Esta estructura aparece en RD_new00.pdf, sección 4, ecuación (3), página PDF 2.
Se adapta a mínimos distintos de cero. La base local está en las ecuaciones (8)
y (9) de notas_documento_base.pdf, sección 3, página PDF 5.

## Condición inicial aleatoria

En las notas, sección 5.2, página PDF 18 / impresa 226, se define

$$
\Delta_G=\{p_G\in\mathbb R_+^N:\sum_i p_{Gi}=P_d\}.
$$

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

### Significado de los parámetros de configuración

- `version: 1`: formato número 1 del archivo JSON. Permite detectar archivos
  incompatibles y no interviene en las ecuaciones.
- `fitness_offset: 3000`: constante $B$ de $f_i$. Es una elección práctica para
  que el fitness sea positivo dentro de todos los intervalos configurados; no es
  un valor obtenido del artículo. El código anterior usaba la misma idea con
  $B=2000$. Aquí $B$ se cancela en cada resta $f_i-f_j$, así que cualquier
  constante común produce la misma trayectoria.
- `step_safety: 0.8`: utiliza el 80 % de una cota conservadora calculada por
  `safe_step_bound()`. Es una decisión numérica de esta implementación, no un
  parámetro del artículo. Ese margen ayuda a que el paso discreto respete límites.
- `period_s: 0.01`: espera real de 0.01 segundos (10 ms) por ronda. Modifica la
  duración física del ensayo, pero no la trayectoria frente a iteraciones.
- `steps: 3000`: cantidad de actualizaciones ejecutadas por cada nodo.

`alpha` no está escrito en el JSON porque `modelo.py` lo calcula usando los
límites, costos y conexiones de la topología:

$$
\alpha=\texttt{step\_safety}\;\alpha_{limite}.
$$

Para cuatro nodos en anillo, $\alpha_{limite}=6.3347\times10^{-11}$ y el 80 %
produce $\alpha=5.06777\times10^{-11}$. Es pequeño porque cada $\hat x_i$
puede valer decenas de miles y la actualización contiene el producto
$\hat x_i\hat x_j$. `alpha` compensa el tamaño de ese producto.

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
