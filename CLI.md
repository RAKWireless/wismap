WisBlock PIN Mapper CLI
==========================

WisMAP is a Python CLI that identifies potential conflicts between modules in a WisBlock integration. Its module catalog is vendored from the **wisblock-data** repository (see [README.md](README.md#updating-module-definitions)); the CLI only reads it.

The CLI shares its business logic (catalog, slot resolution, conflict detection) with the HTTP API documented in [README.md](README.md#http-api). The CLI is the most direct way to script combine analyses or scan the catalog from a terminal; the HTTP API is for integrations and for the bundled web UI.

## Install / Update

At the time being, there is no proper installation procedure so the only way is to manually retrieve the code and install the dependencies. The module catalog ships with the repository — nothing has to be downloaded before the first run.

```
git clone https://github.com/rakwireless/wismap
cd wismap
pip install -r requirements.txt
python3 wismap.py list
```

Updating can be done is a similar fashion:

```
cd wismap
git pull
pip install -r requirements.txt
python3 wismap.py list
```

## Running the code

Alternative ways to run the code are available:

* Using `virtualenv` to isolate the dependencies (requires `virtualenv`, example: `apt install python3-virtualenv`):

    ```
    cd wismap
    virtualenv .env
    . .env/bin/activate
    pip install -r requirements.txt
    python3 wismap.py list
    deactivate
    ```

* Using `make` to encapsulate the previous `virtualenv` procedure (requires `virtualenv` and `make`, example: `apt install python3-virtualenv make`):

    ```
    cd wismap
    make list
    ```

## Usage

```
usage: python wismap.py [-h] [-v] [-m] [-n] action [extra]

positional arguments:
  action          Action to run: list, search, info, combine

options:
  -h, --help      show this help message and exit
  -v, --version   show program's version number and exit
  -m, --markdown  Show tables in markdown format
  -n, --nc        Show NC pins

The 'info' action accepts the name of the module to show as an extra argument.
The 'combine' action accepts a list of modules to mount on the different slots, starting with the base module.
```

### List

Simply lists all the modules available.

```
python3 wismap.py list
```

Example output:

```
┏━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Module    ┃ Type        ┃ Description                                             ┃
┡━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ RAK1901   │ WisSensor   │ RAK1901 WisBlock Temperature and Humidity Sensor        │
│ RAK1902   │ WisSensor   │ RAK1902 WisBlock Barometer Pressure Sensor              │
│ RAK1903   │ WisSensor   │ RAK1903 WisBlock Ambient Light Sensor                   │
│ RAK1904   │ WisSensor   │ RAK1904 WisBlock 3-axis Acceleration Sensor             │
│ RAK1905   │ WisSensor   │ RAK1905 WisBlock 9-AXIS Motion sensor                   │
│ RAK1906   │ WisSensor   │ RAK1906 WisBlock Environmental Sensor                   │
│ RAK1910   │ WisSensor   │ RAK1910 WisBlock GNSS Location Module                   │
│ RAK1920   │ WisIO       │ RAK1920 WisBlock Sensor Adapter Module                  │
│ RAK1921   │ WisModule   │ RAK1921 WisBlock OLED Display                           │
│ RAK2305   │ WisIO       │ RAK2305 WisBlock WiFi Module                            │
│ RAK3372   │ WisCore     │ RAK3372 STM32WLE5 WSisBlock Core                        │
│ RAK4631   │ WisCore     │ RAK4631 nRF52840 WisBlock Core                          │
│ RAK4631-R │ WisCore     │ RAK4631 nRF52840 WisBlock Core RUI                      │
│ RAK5005-O │ WisBase     │ RAK5005-O WisBlock Base Board                           │
│ RAK5801   │ WisIO       │ RAK5801 WisBlock 4-20mA Interface Module                │
│ RAK5802   │ WisIO       │ RAK5802 WisBlock RS485 Interface Module                 │
...

```


### Search

Searches modules by matching a term against the module ID, type, description, and tags. Outputs a filtered list with Module, Type, Description, and Documentation columns.

```
python3 wismap.py search modbus
```

Example output:

```
┌─────────┬───────┬────────────────────────────────┬───────────────────────────────────────────────────────────────────────────┐
│ Module  │ Type  │ Description                    │ Documentation                                                             │
├─────────┼───────┼────────────────────────────────┼───────────────────────────────────────────────────────────────────────────┤
│ RAK5802 │ WisIO │ RAK5802 RS485 Interface Module │ https://docs.rakwireless.com/product-categories/wisblock/rak5802/overview/ │
└─────────┴───────┴────────────────────────────────┴───────────────────────────────────────────────────────────────────────────┘
```

Tags cover protocol/interface (i2c, spi, uart, rs485, modbus, can), communication (lorawan, ble, wifi, nb-iot, gnss, nfc, uwb, ethernet), sensor type (temperature, humidity, pressure, co2, voc, accelerometer, gyroscope), and use case (environmental, motion, industrial, audio, display, storage, power).

### Info

Let's you choose one of the modules and shows basic information for it: description, link to documentation, tags, pin mapping...

```
python3 wismap.py info
```

Example output:

```
[?] Select module:
   RAK12002 RTC Module
   RAK12003 Infrared Temperature Sensor
   RAK12004 MQ2 Gas Sensor Module
   RAK12005 Rain Sensor Module
   RAK12006 PIR Module
   RAK12007 Ultrasonic Module
 > RAK12008 CO2 Gas Sensor
   RAK12009 Alcohol Gas Sensor Module
   RAK12010 Ambient Light Sensor
   RAK12011 WP Barometric Sensor
   RAK12012 Heart Rate Sensor
   RAK12013 3GHz Radar Module
   RAK12014 Laser ToF Module

Module: RAK12008
Type: WisSensor
Description: RAK12008 CO2 Gas Sensor
Chip: Sensirion STC31
Documentation: https://docs.rakwireless.com/product-categories/wisblock/rak12008/overview/
Long: False
I2C Address: 0x2C
Tags: co2, gas, air-quality, environmental, i2c
Mapping:
┌─────┬──────────┐
│ PIN │ Function │
├─────┼──────────┤
│ 2   │ GND      │
│ 7   │ I2C_SCL  │
│ 8   │ I2C_SDA  │
│ 11  │ 3V3_S    │
│ 14  │ 3V3_S    │
│ 17  │ I2C_SDA  │
│ 18  │ I2C_SCL  │
│ 23  │ GND      │
└─────┴──────────┘
Notes:
- I2C address can be changed changing the resistor at R7
- Image: https://images.docs.rakwireless.com/wisblock/rak12008/rak12008.png
- Schematic: https://images.docs.rakwireless.com/wisblock/rak12008/datasheet/rak12008-schematic.png
```

### Combine

This options walks you through different menus to let you choose a base board, a core module and IO and sensor modules for each slot in the base board and then prints out the pin mapping for the whole setup along with information about potential conflicts.

```
python3 wismap.py combine
```

Example output:

```
...
┏━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Function ┃ Base board ┃ Core module ┃ IO_A slot ┃ SENSOR_A slot ┃ SENSOR_B slot ┃ SENSOR_C slot ┃ SENSOR_D slot ┃
┃          ┃ (RAK19007) ┃ (RAK4631)   ┃ (EMPTY)   ┃ (RAK12027)    ┃ (BLOCKED)     ┃ (RAK12002)    ┃ (RAK15006)    ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ I2C_ADDR │            │             │           │               │               │               │               │
│ 3V3      │            │ 3V3         │           │               │               │               │               │
│ 3V3_S    │            │             │           │ 3V3_S         │               │               │               │
│ AIN0     │            │ P0.05       │           │               │               │               │               │
│ AIN1     │            │ P0.31       │           │               │               │               │               │
│ BOOT0    │            │             │           │               │               │               │               │
│ GND      │            │ GND         │           │ GND           │               │ GND           │ GND           │
│ I2C1_SCL │            │ P0.14       │           │ I2C_SCL       │               │ I2C_SCL       │               │
│ I2C1_SDA │            │ P0.13       │           │ I2C_SDA       │               │ I2C_SDA       │               │
│ I2C2_SCL │            │ P0.25       │           │               │               │               │               │
│ I2C2_SDA │            │ P0.24       │           │               │               │               │               │
│ IO1      │            │ P0.17       │           │ INT1          │               │               │               │
│ IO2      │            │ P1.02       │           │ INT2          │               │               │               │
│ IO3      │            │ P0.21       │           │               │               │ CLKOUT        │               │
│ IO4      │            │ P0.04       │           │               │               │ INT1          │               │
│ IO5      │            │ P0.09       │           │               │               │               │ WP            │
│ IO6      │            │ P0.10       │           │               │               │               │               │
│ IO7      │            │ P0.28       │           │               │               │               │               │
│ LED1     │            │ P1.03       │           │               │               │               │               │
│ LED2     │            │ P1.04       │           │               │               │               │               │
│ LED3     │            │ P0.02       │           │               │               │               │               │
│ RESET    │            │ RESET       │           │               │               │               │               │
│ RXD0     │            │ P0.19       │           │               │               │               │               │
│ RXD1     │            │ P0.15       │           │               │               │               │               │
│ SPI_CLK  │            │ P0.03       │           │               │               │               │ SPI_CLK       │
│ SPI_CS   │            │ P0.26       │           │               │               │               │ SPI_CS        │
│ SPI_MISO │            │ P0.29       │           │               │               │               │ SPI_MISO      │
│ SPI_MOSI │            │ P0.30       │           │               │               │               │ SPI_MOSI      │
│ SW1      │            │ P1.01       │           │               │               │               │               │
│ TXD0     │            │ P0.20       │           │               │               │               │               │
│ TXD1     │            │ P0.16       │           │               │               │               │               │
│ USB+     │            │ USB+        │           │               │               │               │               │
│ USB-     │            │ USB-        │           │               │               │               │               │
│ VBAT     │            │             │           │               │               │               │               │
│ VBAT_NRF │            │ VBAT_NRF    │           │               │               │               │               │
│ VBAT_SX  │            │ VBAT_SX     │           │               │               │               │               │
│ VBUS     │            │ VBUS        │           │               │               │               │               │
│ VDD      │            │ VDD         │           │ VDD           │               │ VDD           │               │
│ VDD_NRF  │            │ VDD_NRF     │           │               │               │               │               │
│ VIN      │            │             │           │               │               │               │               │
└──────────┴────────────┴─────────────┴───────────┴───────────────┴───────────────┴───────────────┴───────────────┘
Potential conflicts:
- Possible conflict with 3V3_S enable signal if using IO2
Documentation:
- RAK19007 WisBlock Base Board 2nd Gen: https://docs.rakwireless.com/Product-Categories/WisBlock/RAK19007/
- RAK4631 nRF52840 WisBlock Core: https://docs.rakwireless.com/Product-Categories/WisBlock/RAK4631
- RAK12027 WisBlock Earthquake Sensor: https://docs.rakwireless.com/Product-Categories/WisBlock/RAK12027
- RAK12002 WisBlock RTC Module: https://docs.rakwireless.com/Product-Categories/WisBlock/RAK12002
- RAK15006 WisBlock 512kB FRAM Module: https://docs.rakwireless.com/Product-Categories/WisBlock/RAK15006
```

Alternatively you can provide the full configuration as a list of modules, starting with the base module, the power module (if the base supports it), the IO modules and the sensor modules in order:

```
python wismap.py combine rak6421 rak5802 rak5801 empty empty rak12002 rak18001
```
