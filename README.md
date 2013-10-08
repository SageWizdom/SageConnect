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

(mostly copied from the PlexConnect Page)

1. Follow this (add link) guide to create and add a custom certificate to all of your Apple TVs

2. Download and install SageConnect

3. do more stuff


```sh
# Installation
git clone https://github.com/iBaa/PlexConnect.git
# Updating
cd PlexConnect
git pull
```
> If you don't have Git, you can download [ZIP][] file and extract files to a local directory.

- create HTTPS/SSL certificate
- install certificate to ```assets/certificate/```
- install certificate on aTV

See the [Wiki - Install guides][] for additional documentation.


## Usage

```sh
# Run with root privileges and keep running if logged out
sudo nohup ./PlexConnect.py
```
> Depending on your OS, you might only need ```PlexConnect.py```. Or ```python PlexConnect.py``` or ...

- set your AppleTV's DNS address to the computer running PlexConnect
- run the Trailer App

See the [Wiki - Advanced Settings][] for more details on configuration and advanced settings.


## ToDo

* Learn and reuse the original PlexConnect Template mechanism (currently manually generating all menus)
* Clean up all code (I've horribly uglied up the current PlexConnect release)
* Make this able to run on the same box as the SageTV server (currently on a standalone)
* Make this much much better looking (see item 1, hack)


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
So within some limits, you can do with the code whatever you want. However, if you like and/or want to re-use it, donate to the [PlexConnect][] guys.

The software is provided as is. It might work as expected - or not. Just don't blame us.


[PlexConnect]: https://github.com/iBaa/PlexConnect
[ATVBrowser]: https://github.com/finkdiff/ATVBrowser-script/tree/atvxml
[Plex Forum thread]: http://forums.plexapp.com/index.php/topic/57831-plex-atv-think-different
[ZIP]: https://github.com/iBaa/PlexConnect/archive/master.zip
[Wiki]: https://github.com/iBaa/PlexConnect/wiki
[Wiki - Install guides]: https://github.com/iBaa/PlexConnect/wiki/Install-guides
[Wiki - Advanced Settings]: https://github.com/iBaa/PlexConnect/wiki/Settings-for-advanced-use-and-troubleshooting
[Donation]: http://forums.plexapp.com/index.php/topic/80675-donations-donations/
