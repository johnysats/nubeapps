# Router de la app: / -> carcasa web del simulador, /files -> filebrowser sobre la MicroSD.
# La config va horneada en la imagen a proposito: los *.template de Umbrel pasan por envsubst,
# que se comeria las variables de nginx ($host, $http_upgrade, ...).
#
# Los dos upstreams si son variables, porque la imagen la comparten todas las apps del store
# y cada una tiene que apuntar a SUS contenedores: van por el envsubst del entrypoint de
# nginx, acotado con NGINX_ENVSUBST_FILTER a esas dos para que no toque el resto.
FROM nginx:1.29-alpine
ENV NGINX_ENVSUBST_FILTER='^(SIM|FILES)_HOST$'
COPY default.conf.template /etc/nginx/templates/default.conf.template
COPY 15-require-hosts.sh /docker-entrypoint.d/15-require-hosts.sh
