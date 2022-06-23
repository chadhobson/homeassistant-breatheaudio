# HomeAssistant - BreathAudio BA-6640 6-Zone Amplifier

Python3 interface implementation for the BreatheAudio 6 zone amplifier via rs232 serial. I am using this [USB to RS232 Serial Cable](https://www.amazon.com/gp/product/B00QUZY4UG/ref=ppx_yo_dt_b_search_asin_title) and it's working flawlessly.

This package is a blatant ripoff of https://github.com/johnpez/breatheaudio_6zone_31028 which is a blatant ripoff of https://github.com/etsinko/pybreatheaudio. Any and all credit should go to Egor Tsinko and John Pez, I am just hacking this together to get it to work.

Use at your own risk. I'm not a Python dev, and I'm literally learning HomeAssistant on the fly.

## Installation
- Create a directory called "breatheaudio" under your HA custom_components directory
- Copy the contents of this repo to your breatheaudio directory you just created 
- Now go to Settings -> Devices & Services
- Click "Add Integration" in the bottom right
- Search for "BreatheAudio" and click it
- Fill in your serial port location. Mine was /dev/ttyUSB0 but yours may vary.
- Add the names of each of the six zones
- All done!

## Notes
This is for use with [Home-Assistant](http://home-assistant.io) and BreatheAudio's [BA-6640](https://www.manualslib.com/manual/745331/Breatheaudio-Ba-6640.html) whole home audio amp.
