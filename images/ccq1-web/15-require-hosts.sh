#!/bin/sh
# Sin estas dos el envsubst deja los upstreams vacios y nginx arranca igual, proxeando a
# ninguna parte. Mejor no arrancar y decir cual falta: corre antes del 20-envsubst.
set -e
for var in SIM_HOST FILES_HOST; do
    eval "value=\$$var"
    if [ -z "$value" ]; then
        echo "$0: falta \$$var (nombre completo del contenedor, p.ej. nubeapps-krux_sim_1)" >&2
        exit 1
    fi
done
