# Vocabulario solo para el texto sacado de imágenes

**Esta carpeta está vacía a propósito y lo normal es dejarla así.**

Por defecto, el texto que el OCR saca de una imagen se juzga con **exactamente
las mismas listas** que un mensaje escrito. Es lo que tiene sentido: el spam es
el mismo, llegue en texto o en un cartel, y mantener dos vocabularios en paralelo
solo consigue que uno de los dos se quede atrás sin que nadie se entere.

Los ficheros que pongas aquí se **suman** a los normales, únicamente cuando el
texto viene de una imagen. Tienen el mismo nombre y el mismo formato que los de
`config/blacklist/` (un regex por línea, `#` para comentarios).

## Cuándo usarla

Para términos que en una conversación darían falsos positivos pero que en un
cartel publicitario son inequívocos. Ejemplo real de este proyecto: en un grupo
de Windows, «activación» y «licencia» son palabras del día a día, así que no
pueden ir sueltas en las listas generales; en un cartel, en cambio, casi siempre
forman parte de una oferta.

## Cuándo NO usarla

Si el término también delata spam cuando llega escrito, va en
`config/blacklist/` y no aquí. Duplicarlo en las dos no aporta nada y obliga a
mantener dos sitios.
