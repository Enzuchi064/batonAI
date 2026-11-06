# Lista de materiales — batonAI (prototipo v1)

**Diseño:** ESP32-S3-DevKitC-1 N16R8 alimentado por su propio USB-C. Módulos SPI/I2S conectados directamente por GPIO. Carcasa impresa en 3D. Sin etapas de alimentación adicionales, sin PCB propia y sin componentes discretos redundantes.

## Materiales

| # | Material | Cant. | Especificación | Conexión |
|---:|---|---:|---|---|
| 1 | ESP32-S3-DevKitC-1 **N16R8** | 1 | 16 MB flash, 8 MB PSRAM octal | USB-C 5 V; rail 3,3 V y 5 V a los módulos |
| 2 | Pantalla TFT 3,5" SPI | 1 | 480×320, ST7796S o ILI9488, 3,3 V, sin táctil | 3,3 V, GND, SCLK, MOSI, CS, DC, RST, BL |
| 3 | Módulo INMP441 | 1 | MEMS I2S, 3,3 V | 3,3 V, GND, SCK, WS, SD; L/R a GND |
| 4 | Módulo MAX98357A | 1 | Amplificador I2S, 5 V | 5 V, GND, BCLK, LRC, DIN |
| 5 | Altavoz 8 Ω 1 W | 1 | 28–40 mm | +/− al MAX98357A |
| 6 | Kailh Choc V1 | 2 | Botones A y B | GPIO + GND |
| 7 | Keycap Choc 1u | 2 | A y B | — |
| 8 | Pulsador táctil 12 mm | 5 | 4 para D-pad + 1 para PTT | GPIO + GND |
| 9 | Bisagra de fricción tipo barril | 2 | Eje 6–8 mm, 0,3–0,6 N·m | Tapa y base |
| 10 | Cable de 8 hilos 28 AWG | 1 | 50 cm, silicona flexible | Pantalla a través de la bisagra |
| 11 | Cables Dupont hembra-hembra | 40 | 20 cm | GPIO a GPIO |
| 12 | Tiras de pines 2,54 mm | 2 | 20 pines | Solo si el DevKit no trae headers |
| 13 | Insertos roscados M2,5 | 4 | Latón, inserción térmica | Carcasa |
| 14 | Tornillos M2,5 | 4 | 6–8 mm | Carcasa |
| 15 | Filamento PETG o PLA | ~200 g | 1,75 mm | Carcasa |
| 16 | Cable USB-C | 1 | 1 m | Alimentación |
| 17 | Fuente USB-C 5 V/2 A | 1 | — | Alimentación |

## Conexionado

- **Pantalla:** 8 conductores (3,3 V, GND, SCLK, MOSI, CS, DC, RST, BL). Sin MISO.
- **INMP441:** 3,3 V, GND, SCK, WS, SD. L/R a GND para canal izquierdo.
- **MAX98357A:** 5 V del pin 5V del DevKit, GND, BCLK, LRC, DIN. Altavoz en +/−.
- **Botones:** un lado a GPIO, otro a GND. Pull-up interno del ESP32; sin resistencias externas.
- **Bisagra:** el cable de 8 hilos pasa con holgura y radio amplio; el display va en la tapa.

## No incluido

- Breakout USB-C, interruptor, fusible, ferritas y condensadores externos.
- Batería, protoboard, conectores JST, rejillas, espumas, patas y tornillería extra.
- Herramientas (soldador, estaño, multímetro, calibre, impresora 3D).

## Contingencia

Si al arrancar el amplificador aparecen reinicios o ruido en el audio, añadir un condensador electrolítico de 470 µF entre 5 V y GND junto al MAX98357A. No forma parte del BOM; solo se instala si hace falta.
