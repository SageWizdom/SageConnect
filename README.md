# SageConnect

SageConnect is a SageTV fork of [PlexConnect][].  Right off the bat, major credit and thanks to iBaa, roidy, and elan and all the rest, for their crazy good work on PlexConnect.  Also, many thanks to Nielm and the SageTV developers of..... (update with appropriate credit)

This code is a fork of [PlexConnect][] modified to work with SageTV.  It is currently VERY alpha. Let me repeat, VERY ALPHA.  It works, it streams video and imported media to any AppleTv, but right now it is totally a hack.  That said, please play with this, fix, help, etc.

For more info on [PlexConnect][] their [Wiki][] or just more details on how things work, head over to the original site.


## Pre-Requisites

For this version, you need a SageTV server and a second "SageConnect" server.  The SageConnect server does almost no processing, so it shouldn't need to be high power.  The current iteration expects certain SageTV plug-ins and settings.  The test SageTV server is running:
* SageTV Web Interface plugin
* SageTV Mobile Web Interface plugin
* Nielm's Sage XML Info plugin

The SageConnect server must:
* Any OS (Ubuntu 13.04)
* Python 2.7.4 (installed by default in Ubuntu 13.04
* Network accessable from your AppleTVs
* Network access to your SageTV server


## How To Install

(mostly copied from the [Wiki - Install guides][])

1. Follow this [SSL+ATV][] guide to create and add the custom HTTPS/SSL certificate to all of your Apple TVs

2. Set your AppleTV to use your new servers IP as its DNS server (all else can stay the same)
-- Note, you want to use a static IP for your DNS server

3. Download and install SageConnect via Git or as a [ZIP][] file
```sh
# Installation
git clone https://github.com/SageWizdom/SageConnect.git
# Updating
cd PlexConnect
git pull
```

4. Extract into any directory

5. Copy the certificate to the ```assets/certificate/``` directory

6. Run the code once and kill it (ctrl-c) to generate a config file (Settings.cfg)

7. Configure everything see [Configuring SageConnect][] below

8. Run the code "sudo nohup ./PlexConnect" so that it runs, and continues to run even after you log out.

-- Note: The code will at some point be renamed. Right now this is alpha to get folks running.


See the PlexConnect [Wiki - Install guides][] for additional documentation.


## Usage

```sh
# Run with root privileges and keep running if logged out
sudo nohup ./PlexConnect.py
```
> Depending on your OS, you might only need ```PlexConnect.py```. Or ```python PlexConnect.py``` or ...

ctrl-c will stop the app when running (or sudo killall python)

- set your AppleTV's DNS address to the computer running PlexConnect
- run the Trailer App

See the [Wiki - Advanced Settings][] for more details on configuration and advanced settings.


## Configuring SageConnect
Run Plex connect once, then kill it.  This will create a settings file.  You need to configure these settings
```sh
port_webserver = 80
port_sagetv = 80
port_ssl = 443
ip_plexconnect = (ip of host running this code)
ip_dnsmaster = (your DNS or ex. google 8.8.8.8)
ip_sagetv = (ip of your SageTV server)
ip_webserver = (ip of host running this code)

sagetv_user = sage (or your sagetv username)
sagetv_pass = frey (or your sagetv password)

enable_plexconnect_autodetect = False (must be disabled for now)

certfile = ./assets/certificates/trailers.pem (this should be the name of your cert file)

prevent_atv_update = True (prevent appletv from auto updating)
```

## ToDo / Expected Problems

* Learn and reuse the original PlexConnect Template mechanism (currently manually generating all menus)
* Clean up all code (I've horribly uglied up the current PlexConnect release)
* Make this able to run on the same box as the SageTV server (currently on a standalone)
* Make resume work (currently if you stop, you have to start at begining and fast forward)
* Support streaming live TV (have an idea how to do it, but might be a bit wacky)
* Issue: If you view a currently recording show, it will start at the live time, not at the begining.
* FIXED?: Make this much much better looking (see item 1, hack <-- already started)
* FIXED?: Test with / make work with Linux / MacOS imported media drives <-- currently working on this

## Screenshots
Currently in the screenshots directory (appologies in advance that several of these are blurry, I'll try to grab a better camera and get some images that are not so bad)

1. Image of the AppleTV main screen, notice that the Trailers app is selected ( you access this via the Trailers app)

2. Image of main selection screen (recordings vs imported media)

3. Image of root of imported media directory structure (Windows SageTV Server)

4. Image of root of recorded media listing

5. Image of Simpsons Episode list

6. Image of Simpsons Episode information (The Bob Next Door)

7. Image of the opening sequence playing from the Simpsons


## More detailed Information about the files

* __PlexConnect.py__ - 
Main script file, invoking the DNSServer and WebServer into seperate processes.
* __PlexAPI.py__ - 
Collection of Plex Media Server/MyPlex "connector functions": Auto discovery of running PMSs: Good Day Mate! // XML interface to local PMSs // MyPlex integration
* __DNSServer.py__ - 
This is a small DNS server (hence the name) that is now called whenever aTV needs to resolve an internet address. To hijack the trailer App, we will intercept and re-route all queries to trailers.apple.com. Every other query will be forwarded to the next, your original DNS.
* __WebServer.py__ - 
This script provides the directory content of "assets" to aTV. Additionally it will forward aTV's directory requests to PMS and provide a aTV compatible XML back.
Every media (video, thumbnails...) is URL-wise connected to PMS, so aTV directly accesses the Plex database.
* __XMLConverter.py__ - 
This script contains the XML adaption from Plex Media Server's response to valid aTV XML files.
* __Settings.py__ - 
Basic settings collection. Creates ```Settings.cfg``` at first run - which may be modified externally.
* __ATVSettings.py__ - 
Handles the aTV settings like ViewModes or Transcoder options. Stores aTV settings in ```ATVSettings.cfg```.
* __Localize.py__ -
Holds a couple of utility functions for text translation purposes. Uses dictionaries from ```assets/locales/```.




## License and Disclaimer
(Again, mostly copied from the [PlexConnect][] page)
This software is open-sourced under the MIT Licence (see ```license.txt``` for the full license).
So within some limits, you can do with the code whatever you want. However, if you like and/or want to re-use it, consider a [Donation][] to the [PlexConnect][] guys.

The software is provided as is. It might work as expected - or not. Just don't blame us (or them!).


[SSL+ATV]: http://langui.sh/2013/08/27/appletv-ssl-plexconnect/
[PlexConnect]: https://github.com/iBaa/PlexConnect
[ATVBrowser]: https://github.com/finkdiff/ATVBrowser-script/tree/atvxml
[Plex Forum thread]: http://forums.plexapp.com/index.php/topic/57831-plex-atv-think-different
[ZIP]: https://github.com/SageWizdom/SageConnect/archive/master.zip
[Wiki]: https://github.com/iBaa/PlexConnect/wiki
[Wiki - Install guides]: https://github.com/iBaa/PlexConnect/wiki/Install-guides
[Wiki - Advanced Settings]: https://github.com/iBaa/PlexConnect/wiki/Settings-for-advanced-use-and-troubleshooting
[Donation]: http://forums.plexapp.com/index.php/topic/80675-donations-donations/
