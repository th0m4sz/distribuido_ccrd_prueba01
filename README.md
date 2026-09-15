# CCRD entre placas: guía breve

Cada placa representa un generador y ejecuta el mismo programa. Solo intercambia
su estado con sus vecinos; no existe coordinador de optimización.

## Elegir configuración

| Placas | Anillo | Estrella |
|---|---|---|
| 4 | `4_anillo.json` | `4_estrella.json` |
| 6 | `6_anillo.json` | `6_estrella.json` |

- **Anillo:** 1 conversa con 2, 2 con 3, etc.; el último conversa también con 1.
- **Estrella:** todos conversan con 1. La placa 1 calcula solo su potencia, como las demás.

Para comenzar: anillo con cuatro placas; estrella con seis.
Con los parámetros actuales, el anillo de seis puede quedar bloqueado por
saturación y no llegar al mejor reparto. Se conserva para comparar ambas topologías.

## Ver un ejemplo en el computador

Desde esta carpeta:

```bash
python simular.py --config configuraciones/4_anillo.json --salida resultados/mi_prueba
python graficar.py --carpeta resultados/mi_prueba
```

La imagen `trayectorias.png` contiene solamente:

1. Potencia de cada generador frente a iteraciones.
2. Fitness de cada generador frente a iteraciones.
3. Suma de todas las potencias frente a iteraciones, con la demanda como línea de referencia.

Para graficar se necesita Matplotlib en el computador. El programa de las placas
solo necesita Python 3.9 o posterior, sin paquetes adicionales.

Los cuatro ejemplos ya están en `resultados/4_anillo`, `4_estrella`, `6_anillo`
y `6_estrella`. En cada carpeta, abrir `trayectorias.png`.
El CSV conserva los datos y el JSON permite verificar el ensayo; no es necesario
leerlos para comenzar. No se generan gráficas adicionales.

## Ejecutar en las placas

Copiar a cada placa **nodo.py**, **modelo.py**, **red.py** y **configuraciones/**.
Mantener los nombres `pi-1.local`, etc., si coinciden con los de tus placas.
Todas las placas deben usar el mismo archivo de configuración.

En la placa 1, desde la carpeta del programa:

```bash
python3 nodo.py --config configuraciones/4_anillo.json --id 1 --run-id ensayo_001 --salida resultados/ensayo_001
```

En las demás, cambiar únicamente `--id` por 2, 3 o 4. Para seis, usar
`6_estrella.json` en todas y los ID del 1 al 6.

Cada terminal muestra su potencia cada 500 iteraciones. Cada nodo guarda su CSV y
JSON y termina después de 3 000 iteraciones. Para repetir, usar otro nombre de
ensayo y otra carpeta de salida.

Al terminar, reunir los CSV y JSON de todas las placas en una carpeta del PC:

```bash
python graficar.py --carpeta resultados/ensayo_recogido
```

Ese comando verifica los registros, los combina y dibuja potencia y fitness.
El PC no participa en el cálculo entre placas. Si las redes del PC y del celular
son distintas, hace falta un medio de transferencia entre ellas, por ejemplo
un repositorio en Internet; los nombres `.local` se resuelven dentro de la red local.
No se ha creado un repositorio ni configurado acceso remoto automáticamente.

## Dos observaciones del método

- La suma inicial debe coincidir con la demanda. «Aleatoria» en el artículo significa
  elegida dentro del conjunto factible: distintas potencias cuya suma ya cumple D.
- Si un generador llega a un límite, su fitness puede quedar diferente del de los
  generadores libres. No se debe exigir que todas las curvas de fitness coincidan.

Más detalle matemático: [Nota del modelo](documentacion/BASE_MATEMATICA.md).

## Comprobaciones internas (opcionales)

```bash
python -m unittest discover -s tests -v
python verificar.py
python prueba_local.py --nodos 4 --topologia anillo
python prueba_local.py --nodos 6 --topologia estrella
```

La referencia económica y las verificaciones permanecen como controles internos.
Las pruebas TCP se ejecutan en el PC; aún falta validar en las placas físicas.
Los códigos de `software/prueba inicial` no se modificaron.
