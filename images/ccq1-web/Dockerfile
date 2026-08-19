# Router de la app: / -> noVNC del simulador, /files -> filebrowser sobre la MicroSD.
# La config va horneada en la imagen a proposito: los *.template de Umbrel pasan por envsubst,
# que se comeria las variables de nginx ($host, $http_upgrade, ...).
FROM nginx:1.29-alpine
COPY default.conf /etc/nginx/conf.d/default.conf
