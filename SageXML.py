#!/usr/bin/env python

"""
Sources:

ElementTree
http://docs.python.org/2/library/xml.etree.elementtree.html#xml.etree.ElementTree.SubElement

trailers.apple.com root URL
http://trailers.apple.com/appletv/us/js/application.js
navigation pane
http://trailers.apple.com/appletv/us/nav.xml
->top trailers: http://trailers.apple.com/appletv/us/index.xml
->calendar:     http://trailers.apple.com/appletv/us/calendar.xml
->browse:       http://trailers.apple.com/appletv/us/browse.xml

PlexAPI_getTranscodePath() based on getTranscodeURL from pyplex/plexAPI
https://github.com/megawubs/pyplex/blob/master/plexAPI/info.py
"""


import os
import os.path
import sys
import traceback
import inspect 
import string, cgi, time
import copy  # deepcopy()
from os import sep
import httplib, socket
import base64
from HTMLParser import HTMLParser

import requests
import re

import codecs



try:
    import xml.etree.cElementTree as etree
except ImportError:
    import xml.etree.ElementTree as etree

import time, uuid, hmac, hashlib, base64
from urllib import urlencode
from urlparse import urlparse
from urllib import quote_plus

import Settings, ATVSettings
import PlexAPI
from Debug import *  # dprint()
import Localize



g_param = {}
def setParams(param):
    global g_param
    g_param = param

g_ATVSettings = None
def setATVSettings(cfg):
    global g_ATVSettings
    g_ATVSettings = cfg



# links to CMD class for module wide usage
g_CommandCollection = None



"""
# XML in-place prettyprint formatter
# Source: http://stackoverflow.com/questions/749796/pretty-printing-xml-in-python
"""
def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def XML_prettyprint(XML):
    indent(XML.getroot())
    XML.write(sys.stdout)

def XML_prettystring(XML):
    indent(XML.getroot())
    return(etree.tostring(XML.getroot()))



"""
# aTV XML ErrorMessage - hardcoded XML File
"""
def XML_Error(title, desc):
    errorXML = '\
<?xml version="1.0" encoding="UTF-8"?>\n\
<atv>\n\
    <body>\n\
        <dialog id="com.sample.error-dialog">\n\
            <title>' + title + '</title>\n\
            <description>' + desc + '</description>\n\
        </dialog>\n\
    </body>\n\
</atv>\n\
';
    return errorXML



def XML_PlayVideo_ChannelsV1(path):
    XML = '\
<atv>\n\
  <body>\n\
    <videoPlayer id="com.sample.video-player">\n\
      <httpFileVideoAsset id="' + path + '">\n\
        <mediaURL>http://' + g_param['Addr_PMS'] +  path + '</mediaURL>\n\
        <title>*title*</title>\n\
        <!--bookmarkTime>{{EVAL(Video/viewOffset:0:int(x/1000))}}</bookmarkTime-->\n\
      </httpFileVideoAsset>\n\
    </videoPlayer>\n\
  </body>\n\
</atv>\n\
';
    dprint(__name__,2 , XML)
    return XML



"""
# GetURL
# Source (somewhat): https://github.com/hippojay/plugin.video.plexbmc
# attempted to adjust to use "requests" library to support authentication
"""
def GetURL(address, path):
    try:
        conn = httplib.HTTPConnection(address, timeout=10)


        if g_param['CSettings'].getSetting('sagetv_user')<>'':
            username = g_param['CSettings'].getSetting('sagetv_user')

        if g_param['CSettings'].getSetting('sagetv_pass')<>'':
            password = g_param['CSettings'].getSetting('sagetv_pass')
        
        # base64 encode the username and password
        auth = base64.encodestring('%s:%s' % (username, password)).replace('\n', '')
        conn.putheader("Authorization", "Basic %s" % auth)


        conn.request("GET", path)
        data = conn.getresponse()
        if int(data.status) == 200:
            link=data.read()
            return link
        
        elif ( int(data.status) == 301 ) or ( int(data.status) == 302 ):
            return data.getheader('Location')
        
        elif int(data.status) >= 400:
            error = "HTTP response error: " + str(data.status) + " " + str(data.reason)
            dprint(__name__, 0, error)
            return False
        
        else:
            link=data.read()
            return link

    except socket.gaierror :
        error = "Unable to lookup host: " + g_param['Addr_PMS'] + "\nCheck host name is correct"
        dprint(__name__, 0, error)
        return False
    except socket.error, msg :
        error = "Unable to connect to " + g_param['Addr_PMS'] + "\nReason: " + str(msg)
        dprint(__name__, 0, error)
        return False


"""
# XML converter functions
# - get request from aTV
# - translate and send to PMS
# - receive reply from PMS
# - translate and feed back to aTV
## example STV URLs
## http://sagetv.server/sagem/m/recordings.jsp
## http://sagetv.server/sagem/m/recordings.jsp?title=Cities+of+the+Underworld
## http://sagetv.server/sagem/m/recordings.jsp?title=How+Do+They+Do+It%3f
"""
def XML_ReadFromURL(address, path):
    dprint(__name__, 0, "XML_ReadFromURL {0}:{1}", address, path)

    # send plex specific xargs that sage shouldn't need
    #    xargs = PlexAPI_getXArgs()
    #    if path.find('?')>=0:
    #        path = path + '&' + urlencode(xargs)
    #    else:
    #        path = path + '?' + urlencode(xargs)
    
    XMLstring = GetURL(address, path)
    if XMLstring==False:
        dprint(__name__, 0, 'No Response from SageTV Media Server')
        return False
    
    # parse from memory
    XMLroot = etree.fromstring(XMLstring)    
    
    # XML root to ElementTree
    XML = etree.ElementTree(XMLroot)
    
    dprint(__name__, 1, "====== received XML-PMS ======")
    dprint(__name__, 1, XML_prettystring(XML))
    dprint(__name__, 1, "====== XML-PMS finished ======")
    
    return XML



## modified to use False and hard coded values
# Was discoverPMS (Plex Media Server)
# Now it returns the configured (settings) for the SageTV media Server
def discoverSTV():
    global g_param

#    if g_param['CSettings'].getSetting('enable_plexgdm')=='False':
    if g_param['CSettings'].getSetting('ip_sagetv')=='':
        dprint(__name__, 0, "Settings.cfg: ip_sagetv value not set")

    if g_param['CSettings'].getSetting('port_sagetv')=='':
        dprint(__name__, 0, "Settings.cfg: port_sagetv value not set")

        
    PMS_uuid = 'STV_from_Settings'
    PMS_list = { PMS_uuid:
            {
                'uuid'      : PMS_uuid,
                'serverName': PMS_uuid,
                'ip'        : g_param['CSettings'].getSetting('ip_sagetv'),
                'port'      : g_param['CSettings'].getSetting('port_sagetv'),
            }
        }
    opts = (PMS_uuid, )
    dprint(__name__, 0, "SageTV support hard coded" )
    dprint(__name__, 0, "PlexGDM off - PMS from settings: {0}:{1}", PMS_list[PMS_uuid]['ip'], PMS_list[PMS_uuid]['port'])

    g_ATVSettings.setOptions('pms_uuid', opts)
    g_param['PMS_list'] = PMS_list
    return len(PMS_list)>0


def getXML(textURL):
    """
    Create an example XML file
    """

    # http://sagetv.server/sagem/m/recordings.jsp

    #    address = 'http://sagetv.server'
    #    path = "/sagem/m/recordings.jsp"

    # default username is "sage"
    if g_param['CSettings'].getSetting('sagetv_user')<>'':
        username = g_param['CSettings'].getSetting('sagetv_user')

    # default password is "frey"
    if g_param['CSettings'].getSetting('sagetv_pass')<>'':
        password = g_param['CSettings'].getSetting('sagetv_pass')

    # default password is "port"
    if g_param['CSettings'].getSetting('port_sagetv')<>'':
        port = g_param['CSettings'].getSetting('port_sagetv')

    # get address, path with auth and xml=yes
    #r = requests.get(address + path, auth=(username, password))
    r = requests.get( textURL , auth=(username, password))
    
    if int(r.status_code) == 200:
        dprint(__name__, 2, "code 200")
        dprint(__name__, 2, "encoding: {0}", r.encoding )
#        r.encoding = 'ucs-2'
#        dprint(__name__, 2, "encoding: {0}", r.encoding )

        #        root = etree.fromstring(r.text.encode('utf-8'))
        
        xmlstring = r.text.encode('utf-8')
        xmlstring = re.sub(' xmlns="[^"]+"', '', xmlstring, count=1)
        xmlstring = xmlstring.replace( '&', '&amp;')
        xmlstring = xmlstring.replace( '\'', '&apos;')

        root = etree.fromstring(xmlstring)
        return root
    
    elif ( int(r.status_code) == 301 ) or ( int(r.status_code) == 302 ):
        dprint(__name__, 2, "headers: {0}", r.headers.get('Location') )
        return FALSE
    
    elif int(r.status_code) >= 400:
        error = "HTTP response error: " + str(r.status_code) + " " + str(data.text)
        dprint(__name__, 2, "error: {0}", error )
        return FALSE

'''

 This function creates the top level "trailers" menu.
 It does not read from any external systems.

'''
def makeTopMenu():
    print "====== makeTopMenu ======"

    # Get the IP Address of the SageTV Server
    if g_param['CSettings'].getSetting('ip_sagetv')<>'':
        sage_ip = g_param['CSettings'].getSetting('ip_sagetv')

    # Get the IP of the SageTV Connect Server
    # -- hopefully this is the same server soon
    if g_param['CSettings'].getSetting('ip_webserver')<>'':
        stv_cnct_ip = g_param['CSettings'].getSetting('ip_webserver')

    # default password is "port"
    if g_param['CSettings'].getSetting('port_sagetv')<>'':
        sage_port = g_param['CSettings'].getSetting('port_sagetv')

    
    #<atv>
    #    <head>
    #        <script src="{{URL(:/js/utils.js)}}" />
    #    </head>
    ATVRoot = etree.Element("atv")
    ATVHead = etree.SubElement(ATVRoot, 'head')
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"https://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/utils.js")
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"https://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/settings.js")


    #	<body>
    #		<listWithPreview id="com.sample.list-scroller-split">
    #			<header>
    #				<simpleHeader>
    #					<title>Shows by Name</title>
    #					<subtitle>List all shows by their names</subtitle>
    #				</simpleHeader>
    #			</header>
    ATVBody = etree.SubElement(ATVRoot, 'body')
    ATVListWPreview = etree.SubElement(ATVBody, 'listWithPreview')
    ATVListWPreview.set('id', "com.sample.movie-grid")
    ATVListWPreview.set('volatile', "true")
    ATVListWPreview.set('onVolatileReload', "atv.loadAndSwapURL('http://" + stv_cnct_ip  + "/SageConnect.xml')")

    ATV_LSS_Header = etree.SubElement(ATVListWPreview, 'header')
    ATV_LSS_SimpleHeader = etree.SubElement(ATV_LSS_Header, 'simpleHeader')
    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'title')
    ATV_LSS_SH_Title.text = "SageTV"
    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'subtitle')
    ATV_LSS_SH_Title.text = "Viewing Options"
    
    #        <menu>
    #            <sections>
    #                <menuSection>
    ATV_LSS_Menu = etree.SubElement(ATVListWPreview, 'menu')
    ATV_LSS_Sections = etree.SubElement(ATV_LSS_Menu, 'sections')
    ATV_LSS_MenuSections = etree.SubElement(ATV_LSS_Sections, 'menuSection')

    #        <items>
    ATV_LSS_MS_Items = etree.SubElement(ATV_LSS_MenuSections, 'items')

    href = "atv.loadURL('http://" + stv_cnct_ip + "/recordedShows.xml')"
    label = "Recorded Shows"
    ATV_LSS_MS_MenuItem = etree.SubElement(ATV_LSS_MS_Items, 'oneLineMenuItem')
    ATV_LSS_MS_MenuItem.set("id", "list_1" )
    ATV_LSS_MS_MenuItem.set("onSelect", href )
    ATV_LSS_MS_MenuItemLabel = etree.SubElement(ATV_LSS_MS_MenuItem, 'label')
    ATV_LSS_MS_MenuItemLabel.text = label
    ATV_LSS_MS_MenuItemAcc = etree.SubElement(ATV_LSS_MS_MenuItem, 'accessories')
    etree.SubElement(ATV_LSS_MS_MenuItemAcc, 'arrow')


    href = "atv.loadURL('http://" + stv_cnct_ip + "/mediaPath.xml=')"
    label = "Media Library"
    ATV_LSS_MS_MenuItem = etree.SubElement(ATV_LSS_MS_Items, 'oneLineMenuItem')
    ATV_LSS_MS_MenuItem.set("id", "list_2" )
    ATV_LSS_MS_MenuItem.set("onSelect", href )
    ATV_LSS_MS_MenuItemLabel = etree.SubElement(ATV_LSS_MS_MenuItem, 'label')
    ATV_LSS_MS_MenuItemLabel.text = label
    ATV_LSS_MS_MenuItemAcc = etree.SubElement(ATV_LSS_MS_MenuItem, 'accessories')
    etree.SubElement(ATV_LSS_MS_MenuItemAcc, 'arrow')


    return ATVRoot

'''
Connect to the SageTV server
Download the list of recorded shows
Parse and turn it into an appropriate list
'''
def makeRecordedShowList():
    print "====== makeRecordedShowList ======"

    # Get the IP of the SageTV Server
    if g_param['CSettings'].getSetting('ip_sagetv')<>'':
        sagetv_ip = g_param['CSettings'].getSetting('ip_sagetv')

    # Get the IP of the SageTV Connect Server
    # -- hopefully this is the same server soon
    if g_param['CSettings'].getSetting('ip_webserver')<>'':
        stv_cnct_ip = g_param['CSettings'].getSetting('ip_webserver')

    if g_param['CSettings'].getSetting('sagetv_user')<>'':
        username = g_param['CSettings'].getSetting('sagetv_user')

    if g_param['CSettings'].getSetting('sagetv_pass')<>'':
        password = g_param['CSettings'].getSetting('sagetv_pass')


    #<?xml version="1.0" encoding="UTF-8" ?>
    #<atv>
    #    <head>
    #        <script src="{{URL(:/js/utils.js)}}" />
    #        <script src="{{URL(:/js/settings.js)}}" />
    #    </head>
    ATVRoot = etree.Element("atv")
    ATVHead = etree.SubElement(ATVRoot, 'head')
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"http://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/utils.js")
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"http://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/settings.js")

    #	<body>
    #		<listWithPreview id="com.sample.list-scroller-split">
    #			<header>
    #				<simpleHeader>
    #					<title>Shows by Name</title>
    #					<subtitle>List all shows by their names</subtitle>
    #				</simpleHeader>
    #			</header>
    ATVBody = etree.SubElement(ATVRoot, 'body')
    ATVListWPreview = etree.SubElement(ATVBody, 'listWithPreview')
    ATVListWPreview.set('id', "Show_List")
    ATVListWPreview.set('volatile', "true")
    ATVListWPreview.set('onVolatileReload', "atv.loadAndSwapURL(http://" + stv_cnct_ip + "/recordedShows.xml)")
    
    ATV_LSS_Header = etree.SubElement(ATVListWPreview, 'header')
    ATV_LSS_SimpleHeader = etree.SubElement(ATV_LSS_Header, 'simpleHeader')
    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'title')
    ATV_LSS_SH_Title.text = "Recordings"
    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'subtitle')
    ATV_LSS_SH_Title.text = "All Available Shows"
    

    #    <preview>
    #        <keyedPreview>
    #            <title>&#x00AD;<!--soft-hyphen--></title>
    #            <summary/>
    #            <metadataKeys>
    #                <label>{{TEXT(Version)}}</label>
    #                <label>{{TEXT(Authors)}}</label>
    #                <label>{{TEXT(Wiki/Docs)}}</label>
    #                <label>{{TEXT(Homepage)}}</label>
    #                <label>{{TEXT(Forum)}}</label>
    #            </metadataKeys>
    #            <metadataValues>
    #                <label>Alpha</label>
    #                <label>Baa, roidy</label>
    #                <label>f00b4r</label>
    #                <label>https://github.com/ibaa/plexconnect</label>
    #                <label>http://forums.plexapp.com/index.php/forum/136-appletv-plexconnect/</label>
    #            </metadataValues>
    #            <image>{{URL(:/thumbnails/PlexConnectLogo.jpg)}}</image>
    #        </keyedPreview>
    #    </preview>
    ###
    ###  Not working
    ###
#
#    ATV_LSS_Header = etree.SubElement(ATVListWPreview, 'preview')
#    ATV_LSS_SimpleHeader = etree.SubElement(ATV_LSS_Header, 'keyedPreview')
#    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'title')
#    ATV_LSS_SH_Title.text = "&#x00AD;<!--soft-hyphen-->"
#    etree.SubElement(ATV_LSS_SimpleHeader, 'summary')
#    etree.SubElement(ATV_LSS_SimpleHeader, 'metadataKeys')
#    etree.SubElement(ATV_LSS_SimpleHeader, 'metadataValues')
#    ATV_LSS_SH_Image = etree.SubElement(ATV_LSS_SimpleHeader, 'image')
#    ATV_LSS_SH_Image.text = "http://" + sagetv_ip + "/sagem/m/images/SageLogo256.png"



    #        <menu>
    #            <sections>
    #                <menuSection>
    ATV_LSS_Menu = etree.SubElement(ATVListWPreview, 'menu')
    ATV_LSS_Sections = etree.SubElement(ATV_LSS_Menu, 'sections')
    ATV_LSS_MenuSections = etree.SubElement(ATV_LSS_Sections, 'menuSection')
    
    #    #        <header>
    #    #            <textDivider alignment="center">
    #    #                <title>Genres</title>
    #    #            </textDivider>
    #    #        </header>
    #
    #    ATV_LSS_MS_Header = etree.SubElement(ATV_LSS_MenuSections, 'header')
    #    ATV_LSS_MS_H_TextDivider = etree.SubElement(ATV_LSS_MS_Header, 'textDivider')
    #    ATV_LSS_MS_H_TextDivider.set('alignment','center')
    #    ATV_LSS_MS_H_Title = etree.SubElement(ATV_LSS_MS_H_TextDivider, 'title')
    #    ATV_LSS_MS_H_Title.text = "Shows"
	
    
    #        <items>
    ATV_LSS_MS_Items = etree.SubElement(ATV_LSS_MenuSections, 'items')
    
    # Count is used to generate unique ids
    count = 0
    
    # create new element tree
    ShowList = etree.Element("root")
    
    #
    # Get the XML from the SageTV Server
    #
    stv_address = sagetv_user + ":" + sagetv_pass + "@" + sagetv_ip
    stv_address = "http://" + stv_address
    stv_path = "/sagem/m/recordings.jsp"

    STVRoot = getXML(stv_address+stv_path)

    dprint(__name__, 2, "---> {0}", STVRoot.tag )
    body = STVRoot.find('body')
    
    # for each show
    for div in body.findall('div'):
        if div.get("class") == "content":
            dprint(__name__, 2, "---> <{0} class={1}>", div.tag, div.get('class') )
            
            showlist = div.find('form')
            dprint(__name__, 2, "-----> <{0} method={1}>", showlist.tag, showlist.get('method') )

            for shows in showlist.findall('div'):
                dprint(__name__, 2, "-------> <{0} class={1}>", shows.tag, shows.get('class') )

                title = shows.find('div')
                if title is not None:
                    count = count + 1
                    # ------------------------
                    # Get the show title
                    # ------------------------
                    dprint(__name__, 2, "----------> <{0} class={1}>", title.tag, title.get('class') )
                    thisshow = title.find('a')

                    dprint(__name__, 2, "-----------* {0}", thisshow.text )
                    showname = thisshow.text

                    # ------------------------
                    # Create the call back URL
                    # ------------------------
                    # Get href attribute
                    href = thisshow.get("href")

                    # Grab the "title=abcdefg" text and remove the begining tag
                    href = href[href.index("title="):]
                    href = href[href.index("=") + 1 :]
                    href = href.replace(' ', '*')
                    href = href.replace('\'', '&apos;')

                    # make sure there are no spaces in the href
                    href = "atv.loadURL('http://" + sagetv_ip + "/title=" + href + "')"
                    dprint(__name__, 2, "---- href ---> {0}", href )

                    # add to show list
                    
                    # here is the part that repeats for each show
                    #            <oneLineMenuItem id="list_1">
                    #                <label>Action</label>
                    #                <accessories>
                    #                    <unplayedDot/>
                    #                    <partiallyPlayedDot/>
                    #                </accessories>
                    #                <preview>
                    #                    <crossFadePreview>
                    #                        <image>http://sagetv.server/sagem/MediaFileThumbnail?series=Modern+Marvels</image>
                    #                    </crossFadePreview>
                    #                </preview>
                    #            </twoLineMenuItem>
                    ATV_LSS_MS_MenuItem = etree.SubElement(ATV_LSS_MS_Items, 'oneLineMenuItem')
                    ATV_LSS_MS_MenuItem.set("id", "list_" + str(count) )
                    ATV_LSS_MS_MenuItem.set("onSelect", href )
                    ATV_LSS_MS_MenuItemLabel = etree.SubElement(ATV_LSS_MS_MenuItem, 'label')
                    ATV_LSS_MS_MenuItemLabel.text = showname
                    ATV_LSS_MS_MenuItemAcc = etree.SubElement(ATV_LSS_MS_MenuItem, 'accessories')
                    etree.SubElement(ATV_LSS_MS_MenuItemAcc, 'arrow')
                    ATV_LSS_MS_MI_P = etree.SubElement(ATV_LSS_MS_MenuItem, 'preview')
                    ATV_LSS_MS_MI_P_CFP = etree.SubElement(ATV_LSS_MS_MI_P, 'crossFadePreview')
                    ATV_LSS_MS_MI_P_CFP_I = etree.SubElement(ATV_LSS_MS_MI_P_CFP, 'image')

                    #
                    # http://sagetv.server/sagem/MediaFileThumbnail?series=Extreme+Homes
                    #
                    ATV_LSS_MS_MI_P_CFP_I.text = stv_address + "/sagem/MediaFileThumbnail?series=" + href[href.rfind('='):]

    return ATVRoot

#
# this is a currently unused attempt to create
# a grid layout of titles
# it doesn't currently work
#
def makeTitleGrid():
    dprint(__name__, 2, "====== makeTitleGrid ======" )

    # Get the IP of the SageTV Server
    if g_param['CSettings'].getSetting('ip_sagetv')<>'':
        sagetv_ip = g_param['CSettings'].getSetting('ip_sagetv')

    # Get the IP of the SageTV Connect Server
    # -- hopefully this is the same server soon
    if g_param['CSettings'].getSetting('ip_webserver')<>'':
        stv_cnct_ip = g_param['CSettings'].getSetting('ip_webserver')

    if g_param['CSettings'].getSetting('sagetv_user')<>'':
        username = g_param['CSettings'].getSetting('sagetv_user')

    if g_param['CSettings'].getSetting('sagetv_pass')<>'':
        password = g_param['CSettings'].getSetting('sagetv_pass')


    #<?xml version="1.0" encoding="UTF-8" ?>
    #<atv>
    #    <head>
    #        <script src="{{URL(:/js/utils.js)}}" />
    #        <script src="{{URL(:/js/settings.js)}}" />
    #    </head>
    ATVRoot = etree.Element("atv")
    ATVHead = etree.SubElement(ATVRoot, 'head')
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"https://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/utils.js")
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"https://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/scrobble.js")
    
    #	<body>
    #		<listWithPreview id="com.sample.list-scroller-split">
    #			<header>
    #				<simpleHeader>
    #					<title>Shows by Name</title>
    #					<subtitle>List all shows by their names</subtitle>
    #				</simpleHeader>
    #			</header>
    ATVBody = etree.SubElement(ATVRoot, 'body')
    ATVScroller = etree.SubElement(ATVBody, 'scroller')
    ATVScroller.set('id', "com.sample.show-grid")
    ATVScroller.set('volatile', "true")
    ATVScroller.set('onVolatileReload', "atv.loadAndSwapURL(http://" + stv_cnct_ip + "/SageConnect.xml)")
    
    ATV_S_Header = etree.SubElement(ATVScroller, 'header')
    ATV_S_SimpleHeader = etree.SubElement(ATV_S_Header, 'simpleHeader')
    ATV_S_SH_Title = etree.SubElement(ATV_S_SimpleHeader, 'title')
    ATV_S_SH_Title.text = "Recordings"
    ATV_S_SH_Title = etree.SubElement(ATV_S_SimpleHeader, 'subtitle')
    ATV_S_SH_Title.text = "All Available Shows"
    


    #<items>
    #    <grid columnCount="7" id="grid_0">
    #        <items>
    ATV_S_Items = etree.SubElement(ATVScroller, 'items')
    ATV_S_I_Grid = etree.SubElement(ATV_S_Items, 'grid')
    ATV_S_I_Grid.set("columnCount","5")
    ATV_S_I_Grid.set("id","grid_0")
    ATV_S_I_G_Items = etree.SubElement(ATV_S_I_Grid, 'items')
    

    count = 0
    ShowList = etree.Element("root")
    
    
    #
    # Get the XML from the SageTV Server
    #
    stv_address = sagetv_user + ":" + sagetv_pass + "@" + sagetv_ip
    stv_address = "http://" + stv_address
    stv_path = "/sagem/m/recordings.jsp"

    STVRoot = getXML(stv_address+stv_path)
    
    #    print "---> " + STVRoot.tag
    body = STVRoot.find('body')
    
    # for each show
    for div in body.findall('div'):
        if div.get("class") == "content":
            dprint(__name__, 2, "---> <{0} class={1}>", div.tag, div.get('class') )
            showlist = div.find('form')
            dprint(__name__, 2, "-----> <{0} method={1}>", showlist.tag, showlist.get('method') )



            for shows in showlist.findall('div'):
                dprint(__name__, 2, "-------> <{0} class={1}>", shows.tag, shows.get('class') )
                title = shows.find('div')
                if title <> None:
                    count = count + 1
                    dprint(__name__, 2, "----------> <{0} class={1}>", title.tag, title.get('class') )
                    thisshow = title.find('a')
                    dprint(__name__, 2, "-----------* {0}", thisshow.text )
                    showname = thisshow.text

                    href = thisshow.get("href")
                    href = href[href.index("title="):]
                    href = href[href.index("=") + 1:]
                    href = "atv.loadURL('http://" + stv_cnct_ip + "/title=" + href + "')"
                    dprint(__name__, 2, "---- href ---> {0}", href )

                    # add to show list
                    
                    
                    #    <moviePoster id="{{VAL(key)}}"
                    #    onPlay="atv.sessionStorage['addrpms']='{{ADDR_PMS()}}';{{sendToATV(ratingKey:0:duration:0)}};atv.loadURL('{{URL(key)}}&amp;PlexConnect=Play')"
                    #    onSelect="atv.sessionStorage['addrpms']='{{ADDR_PMS()}}';{{sendToATV(ratingKey:0:duration:0)}};atv.loadURL('{{URL(key)}}&amp;PlexConnect=MoviePrePlay')"
                    #    onHoldSelect="scrobbleMenu('{{TEXT(Movie)}}', '{{VAL(ratingKey)}}', '{{ADDR_PMS()}}');">
                    #        {{COPY(Video)}}
                    #        <title>{{VAL(title)}}</title>
                    #        <subtitle>{{VAL(year)}}</subtitle>
                    #        <image>{{IMAGEURL(thumb)}}</image>
                    #        <defaultImage>resource://Poster.png</defaultImage>
                    #    </moviePoster>
                    
                    ATV_S_I_G_I_mP = etree.SubElement(ATV_S_I_G_Items, 'moviePoster')
                    ATV_S_I_G_I_mP.set("id","item_" + str(count))
                    count = count + 1
                    hdrTemp = "atv.sessionStorage['addrpms']='http://" + stv_cnct_ip + "';{{sendToATV(ratingKey:0:duration:0)}};" + href + "')"
                    ATV_S_I_G_I_mP.set("onPlay",hdrTemp)
                    ATV_S_I_G_I_mP.set("onSelect",hdrTemp)
                    ATV_S_I_G_I_mP.set("onHoldSelect","scrobbleMenu('name', 'rating', 'http://" + stv_cnct_ip + ");" )


                    ATV_S_I_G_I_mP_T = etree.SubElement(ATV_S_I_G_I_mP, 'title')
                    ATV_S_I_G_I_mP_T.text = showname
#                    ATV_S_I_G_I_mP_T = etree.SubElement(ATV_S_I_G_I_mP, 'subtitle')
#                    ATV_S_I_G_I_mP_T.text = title
                    ATV_S_I_G_I_mP_T = etree.SubElement(ATV_S_I_G_I_mP, 'image')
                    ATV_S_I_G_I_mP_T.text = stv_address + "/sagem/MediaFileThumbnail?series" + href[href.rfind('='):href.rfind('\'')]
                    print "--> " + ATV_S_I_G_I_mP_T.text
                    ATV_S_I_G_I_mP_T = etree.SubElement(ATV_S_I_G_I_mP, 'defaultImage')
                    ATV_S_I_G_I_mP_T.text = "resource://16X9.png"

    return ATVRoot

#
# Query the SageTv server and get a list of all eppisodes
# for the selected show
#
def makeShowList(atvTitle):
    dprint(__name__, 2, "====== makeShowList ======: {0}", atvTitle )
        
    # Get the IP of the SageTV Server
    if g_param['CSettings'].getSetting('ip_sagetv')<>'':
        sagetv_ip = g_param['CSettings'].getSetting('ip_sagetv')
    
    # Get the IP of the SageTV Connect Server
    # -- hopefully this is the same server soon
    if g_param['CSettings'].getSetting('ip_webserver')<>'':
        stv_cnct_ip = g_param['CSettings'].getSetting('ip_webserver')
    
    if g_param['CSettings'].getSetting('sagetv_user')<>'':
        username = g_param['CSettings'].getSetting('sagetv_user')
    
    if g_param['CSettings'].getSetting('sagetv_pass')<>'':
        password = g_param['CSettings'].getSetting('sagetv_pass')


    textURL = atvTitle[atvTitle.find("/")+1:]
    dprint(__name__, 2, "--> {0}", textURL )

    textURL = "/sagem/m/recordings.jsp?" + textURL
    textURL = "http://" + username + ":" + password + "@" + sagetv_ip + textURL
    dprint(__name__, 2, "--> {0}", textURL )

    #    http://sagetv.server/sagem/m/recordings.jsp?title=Cities+of+the+Underworld
    
    #<?xml version="1.0" encoding="UTF-8" ?>
    #<atv>
    #    <head>
    #        <script src="{{URL(:/js/utils.js)}}" />
    #        <script src="{{URL(:/js/settings.js)}}" />
    #    </head>
    ATVRoot = etree.Element("atv")
    ATVHead = etree.SubElement(ATVRoot, 'head')
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"https://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/utils.js")
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"https://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/settings.js")
    
    #	<body>
    #		<listWithPreview id="com.sample.list-scroller-split">
    #			<header>
    #				<simpleHeader>
    #					<title>Shows by Name</title>
    #					<subtitle>List all shows by their names</subtitle>
    #				</simpleHeader>
    #			</header>
    ATVBody = etree.SubElement(ATVRoot, 'body')
    ATVListWPreview = etree.SubElement(ATVBody, 'listWithPreview')
    ATVListWPreview.set('id', "Show_List")
    #
    # The loadAndSwapURL needs to be the URL of this page.... not sure I have that?
    #
#    ATVScroller.set('volatile', "true")
#    ATVScroller.set('onVolatileReload', "atv.loadAndSwapURL(http://" + stv_cnct_ip + "/SageConnect.xml)")

    ATV_LSS_Header = etree.SubElement(ATVListWPreview, 'header')
    ATV_LSS_SimpleHeader = etree.SubElement(ATV_LSS_Header, 'simpleHeader')
    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'title')
    ATV_LSS_SH_Title.text = "Recordings"
    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'subtitle')
    ATV_LSS_SH_Title.text = "All Available Shows"
    
    
    #    <preview>
    #        <keyedPreview>
    #            <title>&#x00AD;<!--soft-hyphen--></title>
    #            <summary/>
    #            <metadataKeys>
    #                <label>{{TEXT(Version)}}</label>
    #                <label>{{TEXT(Authors)}}</label>
    #                <label>{{TEXT(Wiki/Docs)}}</label>
    #                <label>{{TEXT(Homepage)}}</label>
    #                <label>{{TEXT(Forum)}}</label>
    #            </metadataKeys>
    #            <metadataValues>
    #                <label>Alpha</label>
    #                <label>Baa, roidy</label>
    #                <label>f00b4r</label>
    #                <label>https://github.com/ibaa/plexconnect</label>
    #                <label>http://forums.plexapp.com/index.php/forum/136-appletv-plexconnect/</label>
    #            </metadataValues>
    #            <image>{{URL(:/thumbnails/PlexConnectLogo.jpg)}}</image>
    #        </keyedPreview>
    #    </preview>
    #
    #    ATV_LSS_Header = etree.SubElement(ATVListWPreview, 'preview')
    #    ATV_LSS_SimpleHeader = etree.SubElement(ATV_LSS_Header, 'keyedPreview')
    #    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'title')
    #    ATV_LSS_SH_Title.text = "&#x00AD;<!--soft-hyphen-->"
    #    etree.SubElement(ATV_LSS_SimpleHeader, 'summary')
    #    etree.SubElement(ATV_LSS_SimpleHeader, 'metadataKeys')
    #    etree.SubElement(ATV_LSS_SimpleHeader, 'metadataValues')
    #    ATV_LSS_SH_Image = etree.SubElement(ATV_LSS_SimpleHeader, 'image')
    #    ATV_LSS_SH_Image.text = "http://sagetv.server/sagem/m/images/SageLogo256.png"
    
    
    
    #        <menu>
    #            <sections>
    #                <menuSection>
    ATV_LSS_Menu = etree.SubElement(ATVListWPreview, 'menu')
    ATV_LSS_Sections = etree.SubElement(ATV_LSS_Menu, 'sections')
    ATV_LSS_MenuSections = etree.SubElement(ATV_LSS_Sections, 'menuSection')
    
    #    #        <header>
    #    #            <textDivider alignment="center">
    #    #                <title>Genres</title>
    #    #            </textDivider>
    #    #        </header>
    #
    #    ATV_LSS_MS_Header = etree.SubElement(ATV_LSS_MenuSections, 'header')
    #    ATV_LSS_MS_H_TextDivider = etree.SubElement(ATV_LSS_MS_Header, 'textDivider')
    #    ATV_LSS_MS_H_TextDivider.set('alignment','center')
    #    ATV_LSS_MS_H_Title = etree.SubElement(ATV_LSS_MS_H_TextDivider, 'title')
    #    ATV_LSS_MS_H_Title.text = "Shows"
	
    
    #        <items>
    ATV_LSS_MS_Items = etree.SubElement(ATV_LSS_MenuSections, 'items')
    
    count = 0
    
    ShowList = etree.Element("root")
    
    #
    # Get the XML from the SageTV Server
    #
    #<html>
    #    <head>
    #    <body>
    #        <div class="header">
    #        <div class="subheader">
    #        <div class="content">
    #            <form method="post">
    STVRoot = getXML(textURL)
    body = STVRoot.find('body')

    # check through each top level div
    for div in body.findall('div'):

        # if this is the content <div>.... keep processing
        #   otherwise skip to next <div>
        if div.get("class") == "content":
            dprint(__name__, 2, "---> <{0} class={1}>", div.tag, div.get('class') )

            # find the <form> sub tag
            showlist = div.find('form')
            dprint(__name__, 2, "---> <{0} method={1}>", showlist.tag, showlist.get('method') )


            #<div class="listcell">
            #    <div class="title">
            #        <input>
            #        <a href="details.jsp?AiringId=10903868">name of show</a>
            #    <div>
            #    <p>
            #        <b>Title of Episode</b>
            #    </p>
            #    <p>Episode description</p>
            #    <p>recording icons (ignore)</p>
            #    <p>date</p>
            #    <p>channel</p>
            #    <p>size / type </p>
            
            # look through all the next level <div> tags
            for shows in showlist.findall('div'):
                count = count + 1
                dprint(__name__, 2, "---> <{0} class={1}>", shows.tag, shows.get('class') )

                if shows.get('class') == 'listcell':

                    # find the next level down <div> tag containing "title
                    title = shows.find('div')
                    if title is not None:
                        dprint(__name__, 2, "----------> <{0} class={1}>", title.tag, title.get('class') )

                        # find the <input> tag containing MediaFileID
                        #<input type="checkbox" name="MediaFileId" value="11031933">
                        mediaid = title.find('input')
                        if mediaid is not None:
                            href = mediaid.get('value')
                        else:
                            XML_Error('makeShowList()','Failed to find a valid MediaID')

                        href = "atv.loadURL('http://" + stv_cnct_ip + "/MediaId=" + href + "')"
                        dprint(__name__, 2, "---- href ---> {0}", href )

                        # Get the show name
                        showid = title.find('a')
                        if showid is not None:
                            showTitle = showid.text
                        else:
                            showTitle = "Unknown"

                        # add to show list
                        
                    episodeTitle = ""
                    episodeDesc = ""
                    episodeDate = ""
                    for eps in shows.findall('p'):
                        if eps.find('b') is not None:
                            # this is the episode title
                            episodeTitle = eps.find('b').text

                        if eps.text is not None and eps.text.find("\"")  > 0:
                            # this is the episode description
                            episodeDesc = eps.text

                        if eps.text is not None and eps.text.find(":") > 0:
                            # this is the original airing time
                            episodeDate = eps.text
                            # grab just the airing date (remove day and time)
                            episodeDate = episodeDate[episodeDate.find(',') + 1:]
                            episodeDate = episodeDate[:episodeDate.rfind(',')]
                            episodeDate = episodeDate.strip()

                        if eps.find('img') is not None:
                            # these are the images that tell view status
                            img = ""


                    # make sure that something is in the title even if its just the show name
                    if episodeTitle == "":
                        episodeTitle = showTitle
                    
                    # here is the part that repeats for each show
                    #            <oneLineMenuItem id="list_1">
                    #                <label>Action</label>
                    #                <accessories>
                    #                    <unplayedDot/>
                    #                    <partiallyPlayedDot/>
                    #                </accessories>
                    #                <preview>
                    #                    <crossFadePreview>
                    #                        <image>http://sagetv.server/sagem/MediaFileThumbnail?series=Modern+Marvels</image>
                    #                    </crossFadePreview>
                    #                </preview>
                    #            </twoLineMenuItem>
                    ATV_LSS_MS_MenuItem = etree.SubElement(ATV_LSS_MS_Items, 'twoLineMenuItem')
                    ATV_LSS_MS_MenuItem.set("id", "list_" + str(count) )
                    ATV_LSS_MS_MenuItem.set("onSelect", href )
                    ATV_LSS_MS_MenuItemLabel = etree.SubElement(ATV_LSS_MS_MenuItem, 'label')
                    ATV_LSS_MS_MenuItemLabel.text = episodeDate + ": " + episodeTitle
                    ATV_LSS_MS_MenuItemLabel = etree.SubElement(ATV_LSS_MS_MenuItem, 'label2')
                    ATV_LSS_MS_MenuItemLabel.text = episodeDesc

    return ATVRoot


def makeMediaInfo(atvAiring):
    dprint(__name__, 2, "====== makeMediaInfo ======: {0}", atvAiring )
        
    # Get the IP of the SageTV Server
    if g_param['CSettings'].getSetting('ip_sagetv')<>'':
        sagetv_ip = g_param['CSettings'].getSetting('ip_sagetv')
    
    # Get the IP of the SageTV Connect Server
    # -- hopefully this is the same server soon
    if g_param['CSettings'].getSetting('ip_webserver')<>'':
        stv_cnct_ip = g_param['CSettings'].getSetting('ip_webserver')
    
    if g_param['CSettings'].getSetting('sagetv_user')<>'':
        username = g_param['CSettings'].getSetting('sagetv_user')
    
    if g_param['CSettings'].getSetting('sagetv_pass')<>'':
        password = g_param['CSettings'].getSetting('sagetv_pass')


    textURL = atvAiring[atvAiring.find("=")+1:]
    dprint(__name__, 2, "--> {0}", textURL )

    textURL = "/sagem/m/details.jsp?MediaFileId=" + textURL
    textURL = "http://" + username + ":" + password + "@" + sagetv_ip + textURL
    dprint(__name__, 2, "--> {0}", textURL )



    # Which you use depends on which ID you have!  ARG
    # http://sagetv.server/sagem/m/details.jsp?AiringId=10904044
    # http://sagetv.server/sagem/m/details.jsp?MediaFileId=10904044



    #
    # Get the XML from the SageTV Server
    #
    #<html>
    #    <head>
    #    <body>
    #        <div class="header">
    #        <div class="subheader">
    #        <div class="content">
    #            <div class="title">
    #            <div class="details">
    #               <video class="title">
    #               <div class="dividerbody">
    #                   <p><b>Episode:</b>Episode title</p>
    #                   <p><b>Description:</b>Episode description</p>
    #                   <p>images of status ex. watched</p>
    #                   <p><img title="rating" alt="rating"></p>
    #                   <p><b>Aired:</b>time date</p>
    #                   <p><b>Duration:</b>30 m</p>
    #                   <p><b>Channel:</b>509-WUSADT</p>
    #                   <p><b>Recorded:</b>9:00 PM - 9:30 PM</p>
    #               <div class="divider">
    #               <div class="dividerbody">
    #                   <p><b>Starring:</b>bob smith</p>
    #                   <p><b>Director:</b>dave smith</p>
    #                   <p><b>Writer:</b>dave smith</p>
    #                   <p><b>Executive Producer:</b>dave smith</p>
    #               <div class="title">
    STVRoot = getXML(textURL)
    body = STVRoot.find('body')

#    showTitle = " "
    epName = ""
    epDescription = ""
    epAired = ""
    epDuration = ""
    epChannel = ""
    epRecorded = ""
    epRating = ""
    epStarring = ""
    epMediaID = ""


    # check through each top level div
    for div1 in body.findall('div'):
        # if this is the content <div>.... keep processing
        #   otherwise skip to next <div>
        if div1.get("class") == "content":

            dprint(__name__, 2, "--div1-->")
            div2 = div1.find('div')
        
            for div2 in div1.findall('div'):
                if div2.get("class") == "title":
                    showTitle = div2.text
                    showTitle = showTitle.strip(' \t\n\r')
                    dprint(__name__, 2, "Show Name--> {0}", showTitle )

                if div2.get("class") == "details":
            
                    for div3 in div2.findall('div'):
                        if div3.get("class") == "dividerbody":
                            for div4 in div3.findall('p'):
                                # find episode name
                                if div4.find('b') <> None and div4.find('b').text == "Episode:":
                                    epName = div4[0].tail
                                    epName = epName.strip(' \t\n\r')
                                    dprint(__name__, 2, "epName --> {0}", epName )

                                # find episode Description
                                if div4.find('b') <> None and div4.find('b').text == "Description:":
                                    epDescription = div4[0].tail
                                    epDescription = epDescription.strip(' \t\n\r')
                                    dprint(__name__, 2, "epDesc --> {0}", epDescription )

                                # find episode Aired
                                if div4.find('b') <> None and div4.find('b').text == "Aired:":
                                    epAired = div4[0].tail
                                    epAired = epAired.strip(' \t\n\r')
                                    dprint(__name__, 2, "epAired --> {0}", epAired )

                                # find episode Duration:
                                if div4.find('b') <> None and div4.find('b').text == "Duration:":
                                    epDuration = div4[0].tail
                                    epDuration = epDuration.strip(' \t\n\r')
                                    dprint(__name__, 2, "epLen --> {0}", epDuration )

                                # find episode Channel:
                                if div4.find('b') <> None and div4.find('b').text == "Channel:":
                                    epChannel = div4[0].tail
                                    epChannel = epChannel.strip(' \t\n\r')
                                    dprint(__name__, 2, "epChannel --> {0}", epChannel )

                                # find episode Recorded:
                                if div4.find('b') <> None and div4.find('b').text == "Recorded:":
                                    epRecorded = div4[0].tail
                                    epRecorded = epRecorded.strip(' \t\n\r')
                                    dprint(__name__, 2, "epRecord --> {0}", epRecorded )

                                # find episode Rating:
                                if div4.find('b') <> None and div4.find('b').text == "Rating:":
                                    epRating = div4[0].tail
                                    epRating = epRating.strip(' \t\n\r')
                                    dprint(__name__, 2, "epRating --> {0}", epRating )

                                # find episode Starring:
                                if div4.find('b') <> None and div4.find('b').text == "Starring:":
                                    epStarring = div4[0].tail
                                    epStarring = epStarring.strip(' \t\n\r')
                                    dprint(__name__, 2, "epStarring --> {0}", epStarring )

                                # find episode MediaFileID:
                                if div4.find('b') <> None and div4.find('b').text == "MediaFileID:":
                                    epMediaID = div4[0].tail
                                    epMediaID = epMediaID.strip(' \t\n\r')
                                    dprint(__name__, 2, "epMediaID --> {0}", epMediaID )


    dprint(__name__, 2, "---> For loop done")

    #<?xml version="1.0" encoding="UTF-8" ?>
    #<atv>
    #    <head>
    #        <script src="{{URL(:/js/utils.js)}}" />
    #        <script src="{{URL(:/js/selectAudioAndSubs.js)}}" />
    #    </head>
    ATVRoot = etree.Element("atv")
    ATVHead = etree.SubElement(ATVRoot, 'head')
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"https://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/utils.js")
#    ATVtemp = etree.SubElement(ATVHead, 'script')
#    ATVtemp.set('src',"https://sagetvconnect.server/home/tv/PlexConnect/assets/js/selectAudioAndSubs.js")


    #<body>
    #    <itemDetail id="com.apple.trailer" volatile="true" onVolatileReload="atv.loadAndSwapURL('this url')">
    #        <title>{{VAL(Video/title)}} ({{VAL(Video/year)}})</title>
    #        <subtitle>{{VAL(Video/studio)}}</subtitle>
    #        <rating>{{contentRating(Video/contentRating)}}</rating>
    #        <summary>{{VAL(Video/summary)}}</summary>
    #        <image style="moviePoster">{{BIGIMAGEURL(Video/thumb)}}</image>
    #        <defaultImage>resource://Poster.png</defaultImage>

    ATVBody = etree.SubElement(ATVRoot, 'body')
    ATVItemDetail = etree.SubElement(ATVBody, 'itemDetail')
    ATVItemDetail.set('id', "com.apple.trailer")
    #    ATVItemDetail('volatile', "true")
    #    ATVItemDetail('onVolatileReload', "atv.loadAndSwapURL(http://sagetvconnect.server"+atvAiring+")")


    ATV_ID_Title = etree.SubElement(ATVItemDetail, 'title')
    if epName is "":
        epName = showTitle + epAired[epAired.find(','):epAired.rfind(',')]
    ATV_ID_Title.text = epName
    ATV_ID_SubTitle = etree.SubElement(ATVItemDetail, 'subtitle')
    ATV_ID_SubTitle.text = showTitle
    ATV_ID_Rating = etree.SubElement(ATVItemDetail, 'rating')
    ATV_ID_Rating.text = epRating
    ATV_ID_Summary = etree.SubElement(ATVItemDetail, 'summary')
    if epName is not "":
        ATV_ID_Summary.text = epDescription
    ATV_ID_BigPoster = etree.SubElement(ATVItemDetail, 'image')
    ATV_ID_BigPoster.set("style","moviePoster")

    posterTmp = "http://" + username + ":" + password + "@" + sagetv_ip + textURL
    ATV_ID_BigPoster.text = posterTmp + "/stream/MediaFileThumbnailServlet?MediaFileId=" + epMediaID
    ATV_ID_DefImage = etree.SubElement(ATVItemDetail, 'defaultImage')
    ATV_ID_DefImage.text = "resource://Poster.png"


    #<table>
    ATV_ID_Table = etree.SubElement(ATVItemDetail, 'table')

    #    <columnDefinitions>
    #        <columnDefinition width="25" alignment="left">
    #            <title>{{TEXT(Details)}}</title>
    #        </columnDefinition>
    #        <columnDefinition width="25" alignment="left">
    #            <title>{{TEXT(Actors)}}</title>
    #        </columnDefinition>
    #        <columnDefinition width="25" alignment="left">
    #            <title>{{TEXT(Directors)}}</title>
    #        </columnDefinition>
    #        <columnDefinition width="25" alignment="left">
    #            <title>{{TEXT(Producers)}}</title>
    #        </columnDefinition>
    #    </columnDefinitions>
    ATV_ID_T_CD = etree.SubElement(ATV_ID_Table, 'columnDefinitions')

    ColumnDefinitionText = ['Details', 'Actors', 'Directors', 'Producers']
    for cdCount in range (0,4):
        ATV_ID_T_CD1 = etree.SubElement(ATV_ID_T_CD, 'columnDefinition')
        ATV_ID_T_CD1.set("width","25")
        ATV_ID_T_CD1.set("alignment","left")
        ATV_ID_T_CD1_title = etree.SubElement(ATV_ID_T_CD1, 'title')
        ATV_ID_T_CD1_title.text = ColumnDefinitionText[cdCount]

    #    <rows>
    #        <row>
    #            <label>{{VAL(Video/Genre/tag)}}</label>
    #            <label>{{VAL(Video/Role/tag)}}</label>
    #            <label>{{VAL(Video/Director/tag)}}</label>
    #            <label>{{VAL(Video/Producer/tag)}}</label>
    #        </row>
    ATV_ID_T_Rows = etree.SubElement(ATV_ID_Table, 'rows')
    
    rowText = ['Genre tag', 'Role tag', 'Director tag', 'Producer tag']
    ATV_ID_T_Row = etree.SubElement(ATV_ID_T_Rows, 'row')
    for cdCount in range (0,4):
        ATV_ID_T_Row_Label = etree.SubElement(ATV_ID_T_Row, 'label')
        ATV_ID_T_Row_Label.text = rowText[cdCount]

    #        <row>
    #            <label>{{getDurationString(Video/duration)}}</label>
    #            <label>{{VAL(Video/Role[2]/tag)}}</label>
    #            <label>{{VAL(Video/Director[2]/tag)}}</label>
    #            <label>{{VAL(Video/Producer[2]/tag)}}</label>
    #        </row>
    rowText = ['duration', 'Role tag2', 'Director tag2', 'Producer tag2']
    ATV_ID_T_Row = etree.SubElement(ATV_ID_T_Rows, 'row')
    for cdCount in range (0,4):
        ATV_ID_T_Row_Label = etree.SubElement(ATV_ID_T_Row, 'label')
        ATV_ID_T_Row_Label.text = rowText[cdCount]

    #        <row>
    #            <label>{{VAL(Video/Media/videoResolution:Unknown:1080=1080p|720=720p|576=SD|480=SD|sd=SD)}}   {{VAL(Video/Media/audioCodec:Unknown:ac3=AC3|aac=AAC|mp3=MP3|dca=DTS|drms=DRMS)}} {{VAL(Video/Media/audioChannels:Unknown:2=Stereo|6=5.1|8=7.1)}} </label>
    #            <label>{{VAL(Video/Role[3]/tag)}}</label>
    #            <label>{{VAL(Video/Director[3]/tag)}}</label>
    #            <label>{{VAL(Video/Producer[3]/tag)}}</label>
    #        </row>
    rowText = ['1080p AC3 5.1', 'Role tag3', 'Director tag3', 'Producer tag3']
    ATV_ID_T_Row = etree.SubElement(ATV_ID_T_Rows, 'row')
    for cdCount in range (0,4):
        ATV_ID_T_Row_Label = etree.SubElement(ATV_ID_T_Row, 'label')
        ATV_ID_T_Row_Label.text = rowText[cdCount]

    #        <row>
    #            <starRating hasUserSetRating="true">
    #                <percentage>{{EVAL(Video/userRating:0:int(x*10))}}</percentage>
    #            </starRating>{{CUT(Video/userRating:CUT:0=)}}
    #            <starRating>
    #                <percentage>{{EVAL(Video/rating:0:int(x*10))}}</percentage>
    #            </starRating>{{CUT(Video/userRating::0=CUT)}}
    #            <label>{{VAL(Video/Role[4]/tag)}}</label>
    #            <label>{{VAL(Video/Director[4]/tag)}}</label>
    #            <label>{{VAL(Video/Producer[4]/tag)}}</label>
    #        </row>
    rowText = ['--', 'Role tag3', 'Director tag3', 'Producer tag3']
    ATV_ID_T_Row = etree.SubElement(ATV_ID_T_Rows, 'row')
    ATV_ID_T_Row_Star = etree.SubElement(ATV_ID_T_Row, 'starRating')
    ATV_ID_T_Row_Star.set("hasUserSetRating", "true")
    ATV_ID_T_Row_S_Pct = etree.SubElement(ATV_ID_T_Row_Star, 'percentage')
    ATV_ID_T_Row_S_Pct.text = "50"

    for cdCount in range (1,4):
        ATV_ID_T_Row_Label = etree.SubElement(ATV_ID_T_Row, 'label')
        ATV_ID_T_Row_Label.text = rowText[cdCount]



    #</table>
    #<centerShelf>
    #    <shelf id="centerShelf" columnCount="4" center="true">
    #        <sections>
    #            <shelfSection>
    ATV_ID_CS = etree.SubElement(ATVItemDetail, 'centerShelf')
    ATV_ID_CS_S = etree.SubElement(ATV_ID_CS, 'shelf')
    ATV_ID_CS_S.set("id","centerShelf")
    ATV_ID_CS_S.set("columnCount","4")
    ATV_ID_CS_S.set("center","true")
    ATV_ID_CS_S_S = etree.SubElement(ATV_ID_CS_S, 'sections')
    ATV_ID_CS_S_S_SS = etree.SubElement(ATV_ID_CS_S_S, 'shelfSection')

    #                            <items>
    ATV_ID_CS_S_S_SS_I = etree.SubElement(ATV_ID_CS_S_S_SS, 'items')

    #    <actionButton id="play" onSelect="atv.sessionStorage['addrpms']='{{ADDR_PMS()}}';atv.loadURL('{{URL(key)}}&amp;PlexConnect=Play')"
    #    onPlay="atv.sessionStorage['addrpms']='{{ADDR_PMS()}}';atv.loadURL('{{URL(key)}}&amp;PlexConnect=Play')">
    #        <title>{{TEXT(Play)}}</title>
    #        <image>resource://Play.png</image>
    #        <focusedImage>resource://PlayFocused.png</focusedImage>
    #        <!--<badge></badge>-->
    #    </actionButton>
    ATV_ID_CS_S_S_SS_I_AB = etree.SubElement(ATV_ID_CS_S_S_SS_I, 'actionButton')
    ATV_ID_CS_S_S_SS_I_AB.set("id","play")
    TempStr = "atv.sessionStorage['addrpms']='" + stv_cnct_ip + "';atv.loadURL('" + stv_cnct_ip + "/MediaFileId=" + epMediaID + "')"
    ATV_ID_CS_S_S_SS_I_AB.set("onSelect",TempStr)
    ATV_ID_CS_S_S_SS_I_AB.set("onPlay",TempStr)
    ATV_ID_CS_S_S_SS_I_AB_Title = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'title')
    ATV_ID_CS_S_S_SS_I_AB_Title.text = "Play"
    ATV_ID_CS_S_S_SS_I_AB_Img = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'image')
    ATV_ID_CS_S_S_SS_I_AB_Img.text = "resource://Play.png"
    ATV_ID_CS_S_S_SS_I_AB_Img = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'focusedImage')
    ATV_ID_CS_S_S_SS_I_AB_Img.text = "resource://PlayFocused.png"

    #    <actionButton id="selectAudioAndSubs" onSelect="selectAudioAndSubs('{{ADDR_PMS()}}', '{{VAL(Video/Media/Part/id)}}')"
    #        onPlay="selectAudioAndSubs('{{ADDR_PMS()}}', '{{VAL(Video/Media/Part/id)}}')">
    #            <title>{{TEXT(Audio/Subs)}}</title>
    #            <image>resource://Queue.png</image>
    #            <focusedImage>resource://QueueFocused.png</focusedImage>
    #    </actionButton>
#    ATV_ID_CS_S_S_SS_I_AB = etree.SubElement(ATV_ID_CS_S_S_SS_I, 'actionButton')
#    ATV_ID_CS_S_S_SS_I_AB.set("id","selectAudioAndSubs")
#    TempStr = "atv.sessionStorage['addrpms']='" + stv_cnct_ip + "';atv.loadURL('http://sagetvconnect.server/stream/HTTPLiveStreamingPlaylist?MediaFileId=10960584')"
#    ATV_ID_CS_S_S_SS_I_AB.set("onSelect",TempStr)
#    ATV_ID_CS_S_S_SS_I_AB.set("onPlay",TempStr)
#    ATV_ID_CS_S_S_SS_I_AB_Title = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'title')
#    ATV_ID_CS_S_S_SS_I_AB_Title.text = "Audio Sub"
#    ATV_ID_CS_S_S_SS_I_AB_Img = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'image')
#    ATV_ID_CS_S_S_SS_I_AB_Img.text = "resource://Queue.png"
#    ATV_ID_CS_S_S_SS_I_AB_Img = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'focusedImage')
#    ATV_ID_CS_S_S_SS_I_AB_Img.text = "PlayFocused.png://QueueFocused.png"

    #    <actionButton id="more" accessibilityLabel="More info" onSelect="atv.showMoreInfo();" onPlay="atv.showMoreInfo();">
    #        <title>{{TEXT(More)}}</title>
    #        <image>resource://More.png</image>
    #        <focusedImage>resource://MoreFocused.png</focusedImage>
    #    </actionButton>
    ATV_ID_CS_S_S_SS_I_AB = etree.SubElement(ATV_ID_CS_S_S_SS_I, 'actionButton')
    ATV_ID_CS_S_S_SS_I_AB.set("id","selectAudioAndSubs")
    TempStr = "atv.sessionStorage['addrpms']='" + stv_cnct_ip + "';atv.loadURL('http://" + stv_cnct_ip + "/MediaFileId=" + epMediaID + "')"
    ATV_ID_CS_S_S_SS_I_AB.set("onSelect",TempStr)
    ATV_ID_CS_S_S_SS_I_AB.set("onPlay",TempStr)
    ATV_ID_CS_S_S_SS_I_AB_Title = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'title')
    ATV_ID_CS_S_S_SS_I_AB_Title.text = "More"
    ATV_ID_CS_S_S_SS_I_AB_Img = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'image')
    ATV_ID_CS_S_S_SS_I_AB_Img.text = "resource://More.png"
    ATV_ID_CS_S_S_SS_I_AB_Img = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'focusedImage')
    ATV_ID_CS_S_S_SS_I_AB_Img.text = "resource://MoreFocused.png"



#    #    </items>
#    #    <stash>
#    ATV_ID_CS_S_S_SS_S = etree.SubElement(ATV_ID_CS_S_S_SS, 'stash')
#
#    #        <stream>
#    #            {{COPY(Video/Media/Part/Stream)}}
#    #            <id>{{VAL(id:0)}}</id>
#    #            <language>{{VAL(language:Unknown)}}</language>
#    #            <format>{{VAL(format:UNK)}}</format>
#    #            <codec>{{VAL(codec)}}</codec>
#    #            <streamType>{{VAL(streamType:0)}}</streamType>
#    #                <selected>{{VAL(selected:0)}}</selected>
#    #        </stream>
#    ATV_ID_CS_S_S_SS_S_S = etree.SubElement(ATV_ID_CS_S_S_SS_S, 'stream')
#    ATV_ID_CS_S_S_SS_S_S_Tmp = etree.SubElement(ATV_ID_CS_S_S_SS_S_S, 'id')
#    ATV_ID_CS_S_S_SS_S_S_Tmp.text = "256"
#    ATV_ID_CS_S_S_SS_S_S_Tmp = etree.SubElement(ATV_ID_CS_S_S_SS_S_S, 'language')
#    ATV_ID_CS_S_S_SS_S_S_Tmp.text = "English"
#    ATV_ID_CS_S_S_SS_S_S_Tmp = etree.SubElement(ATV_ID_CS_S_S_SS_S_S, 'format')
#    ATV_ID_CS_S_S_SS_S_S_Tmp.text = "planar 4:2:0 YUV"
#    ATV_ID_CS_S_S_SS_S_S_Tmp = etree.SubElement(ATV_ID_CS_S_S_SS_S_S, 'codec')
#    ATV_ID_CS_S_S_SS_S_S_Tmp.text = "H264 - MPEG-4 AVC (part 10)(h264)"
#    ATV_ID_CS_S_S_SS_S_S_Tmp = etree.SubElement(ATV_ID_CS_S_S_SS_S_S, 'streamType')
#    ATV_ID_CS_S_S_SS_S_S_Tmp.text = "English"
#    ATV_ID_CS_S_S_SS_S_S_Tmp = etree.SubElement(ATV_ID_CS_S_S_SS_S_S, 'selected')
#    ATV_ID_CS_S_S_SS_S_S_Tmp.text = "English"


#            </centerShelf>
#            <!--
#            <divider>
#                <smallCollectionDivider alignment="left">
#                    <title>Actors</title>
#                </smallCollectionDivider>
#            </divider>{{CUT(Video/Role/id:CUT:=)}}
#            
#            <bottomShelf>
#                <shelf id="bottomShelf" columnCount="7">
#                    <sections>
#                        <shelfSection>
#                            <items>
#                                <moviePoster related="true" alwaysShowTitles="true" id="shelf_item_1" onSelect="atv.loadURL('http://trailers.apple.com/library/sections/{{VAL(/librarySectionID)}}/actor/{{VAL(id)}}/')">
#                                    {{COPY(Video/Role)}}
#                                    <title>{{VAL(tag)}}</title>
#                                    <subtitle>as {{VAL(role)}}</subtitle>
#                                    <image>{{IMAGEURL(thumb)}}</image>
#                                    <defaultImage>http://{{ADDR_PMS()}}/:/resources/actor-icon.png</defaultImage>
#                                </moviePoster>
#                            </items>
#                        </shelfSection>
#                    </sections>
#                </shelf>
#            </bottomShelf>{{CUT(Video/Role/id:CUT:=)}}
#            -->

#            <moreInfo>{{VAR(cut:NoKey:CUT)}}  <!--this sets the var to CUT-->
#                <listScrollerSplit id="com.sample.list-scroller-split">
#                    <menu>
#                        <sections>
#                            <menuSection>
#                                <header>
#                                    <textDivider alignment="left" accessibilityLabel="Genres">
#                                        <title>{{TEXT(Genres)}}</title>
#                                    </textDivider>
#                                </header>
#                                <items>
#                                    <oneLineMenuItem id="list_2">
#                                        {{COPY(Video/Genre)}}
#                                        {{VAR(cut:NoKey:)}}  <!--this sets the var to None-->
#                                        <label>{{VAL(tag)}}</label>
#                                        <preview>
#                                            <link>{{URL(:/library/sections/)}}{{VAL(/librarySectionID)}}/genre/{{VAL(id)}}?X-Plex-Container-Start=0&amp;X-Plex-Container-Size=50&amp;PlexConnect=MoviePreview</link>
#                                        </preview>
#                                    </oneLineMenuItem>
#                                </items>
#                            </menuSection>{{CUT(Video/Genre/id:CUT:=)}}
#                            
#                            <menuSection>
#                                <header>
#                                    <textDivider alignment="left" accessibilityLabel="Directors">
#                                        <title>{{TEXT(Directors)}}</title>
#                                    </textDivider>
#                                </header>
#                                <items>
#                                    <oneLineMenuItem id="list_3" accessibilityLabel="Ivan Reitman">
#                                        {{COPY(Video/Director)}}
#                                        {{VAR(cut:NoKey:)}}  <!--this sets the var to None-->
#                                        <label>{{VAL(tag)}}</label>
#                                        <preview>
#                                            <link>{{URL(:/library/sections/)}}{{VAL(/librarySectionID)}}/director/{{VAL(id)}}/&amp;PlexConnect=MoviePreview</link>
#                                        </preview>
#                                    </oneLineMenuItem>
#                                </items>
#                            </menuSection>{{CUT(Video/Director/id:CUT:=)}}
#                            
#                            <menuSection>
#                                <header>
#                                    <textDivider alignment="left" accessibilityLabel="Actors">
#                                        <title>{{TEXT(Actors)}}</title>
#                                    </textDivider>
#                                </header>
#                                <items>
#                                    <twoLineMenuItem id="list_0" accessibilityLabel="Natalie Portman">
#                                        {{COPY(Video/Role)}}
#                                        {{VAR(cut:NoKey:)}}  <!--this sets the var to None-->
#                                        <label>{{VAL(tag)}}</label>
#                                        <label2>{{VAL(role)}}</label2>
#                                        <image>{{IMAGEURL(thumb)}}</image>
#                                        <defaultImage>resource://Poster.png</defaultImage>
#                                        <preview>
#                                            <link>{{URL(:/library/sections/)}}{{VAL(/librarySectionID)}}/actor/{{VAL(id)}}/&amp;PlexConnect=MoviePreview</link>
#                                        </preview>
#                                    </twoLineMenuItem>
#                                </items>
#                            </menuSection>{{CUT(Video/Role/id:CUT:=)}}
#                        
#                        </sections>
#                    </menu>
#                </listScrollerSplit>
#            </moreInfo>{{CUT(#cut)}}
#                             
# </itemDetail>
# </body>
# </atv>

    return ATVRoot


def makePlay(atvAiring):
    dprint(__name__, 2, "====== makePlay ======: {0}", atvAiring )
    
    # Get the IP of the SageTV Server
    if g_param['CSettings'].getSetting('ip_sagetv')<>'':
        sagetv_ip = g_param['CSettings'].getSetting('ip_sagetv')
    
    # Get the IP of the SageTV Connect Server
    # -- hopefully this is the same server soon
    if g_param['CSettings'].getSetting('ip_webserver')<>'':
        stv_cnct_ip = g_param['CSettings'].getSetting('ip_webserver')
    
    if g_param['CSettings'].getSetting('sagetv_user')<>'':
        username = g_param['CSettings'].getSetting('sagetv_user')
    
    if g_param['CSettings'].getSetting('sagetv_pass')<>'':
        password = g_param['CSettings'].getSetting('sagetv_pass')
    
    textURL = atvAiring[atvAiring.find("/")+1:]
    dprint(__name__, 2, "--> {0}", textURL )

    textURL = "/stream/HTTPLiveStreamingPlaylist?" + textURL
    textURL = "http://" + username + ":" + password + "@" + sagetv_ip + textURL
    dprint(__name__, 2, "--> {0}", textURL )

    # "http://sagetv.server/stream/HTTPLiveStreamingPlaylist?MediaFileId=10960584"
    
    
    #<atv>
    #    <body>
    #        <videoPlayer id="com.sample.video-player">
    #            <httpFileVideoAsset id="{{VAL(Video/key)}}">
    ATVRoot = etree.Element("atv")
    ATVBody = etree.SubElement(ATVRoot, 'body')
    ATV_VP = etree.SubElement(ATVBody, 'videoPlayer')
    ATV_VP.set('id', "com.sample.video-player")
    ATV_VP_hFVA = etree.SubElement(ATV_VP, 'httpFileVideoAsset')
    ATV_VP_hFVA.set('id', "video-key")

    #                <mediaURL>{{MEDIAURL(Video)}}</mediaURL>
    #                <title>{{VAL(Video/title)}}</title>
    #                <description>{{VAL(Video/summary)}}</description>
    #                <bookmarkTime>{{EVAL(Video/viewOffset:0:int(x/1000))}}</bookmarkTime>
    #                <image>{{IMAGEURL(Video/thumb)}}</image>
    ATV_VP_hFVA_mU = etree.SubElement(ATV_VP_hFVA, 'mediaURL')
    ATV_VP_hFVA_mU.text = textURL

    ATV_VP_hFVA_mU = etree.SubElement(ATV_VP_hFVA, 'title')
    ATV_VP_hFVA_mU.text = "title"

    ATV_VP_hFVA_mU = etree.SubElement(ATV_VP_hFVA, 'description')
    ATV_VP_hFVA_mU.text = "desc"

# FIX
# resume not currently supported
# resume from some position within the file stream
# the number is seconds000  so 20 seconds would be "20000"
#    ATV_VP_hFVA_mU = etree.SubElement(ATV_VP_hFVA, 'bookmarkTime')
#    ATV_VP_hFVA_mU.text = "1438262"

    ATV_VP_hFVA_mU = etree.SubElement(ATV_VP_hFVA, 'image')
    ATV_VP_hFVA_mU.text = ""

    #
    #                <!-- stacked media -->
    #                <myMetadata>
    #                    <httpFileVideoAsset id="{{VAL(key)}}">
    #                        <mediaURL>http://{{ADDR_PMS()}}{{VAL(key)}}</mediaURL>
    #                        <title>{{VAL(@main/Video/title)}}</title>
    #                        <description>{{VAL(@main/Video/summary)}}</description>
    #                        <!--bookmarkTime>{{EVAL(@main/Video/viewOffset:0:int(x/1000))}}</bookmarkTime-->
    #                        <image>{{IMAGEURL(@main/Video/thumb)}}</image>
    #                    </httpFileVideoAsset>{{COPY(Video/Media/Part)}}
    #                </myMetadata>
    #            
    #            </httpFileVideoAsset>
    #        </videoPlayer>
    #    </body>
    #</atv>

    return ATVRoot



def makeDirTree():
    # Specifically build imported media tree
    # this will look to see if we have saved a dir tree, if not, it will generate the xml and save it.
    # how often do I need to regenerate?  once a month ish?
    dprint(__name__, 2, "====== makeDirTree ======" )
        
    # Get the IP of the SageTV Server
    if g_param['CSettings'].getSetting('ip_sagetv')<>'':
        sagetv_ip = g_param['CSettings'].getSetting('ip_sagetv')
    
    # Get the IP of the SageTV Connect Server
    # -- hopefully this is the same server soon
    if g_param['CSettings'].getSetting('ip_webserver')<>'':
        stv_cnct_ip = g_param['CSettings'].getSetting('ip_webserver')
    
    if g_param['CSettings'].getSetting('sagetv_user')<>'':
        username = g_param['CSettings'].getSetting('sagetv_user')
    
    if g_param['CSettings'].getSetting('sagetv_pass')<>'':
        password = g_param['CSettings'].getSetting('sagetv_pass')
    
    textURL = "/sage/Search?SearchString=&searchType=MediaFiles&Video=on&search_fields=title&filename=&TimeRange=0&Categories=**Any**&Channels=**Any**&watched=any&dontlike=any&favorite=any&firstruns=any&hdtv=any&archived=any&manrec=any&autodelete=any&partials=none&sort1=title_asc&sort2=none&grouping=None&pagelen=100&xml=yes"

    textURL = "http://" + username + ":" + password + "@" + sagetv_ip + textURL
    dprint(__name__, 2, "--> {0}", textURL )

    #<sageShowInfo version="1.3">
    #    <showList>
    STVRoot = getXML(textURL)
    STVRoot_sL = STVRoot.find('showList')
    
    IMT_Root = etree.Element("ImportMediaTree")
    
    
    #<show epgId="MF10490770">
    #    <title>#West-Wing-Central@Dalnet</title>
    #    <episode>#West-Wing-Central@Dalnet</episode>
    #    <airing channelId="0" duration="156" sageDbId="10490772" startTime="2013-07-15T09:39:24.10Z">
    #        <recordSchedule duration="156" startTime="2013-07-15T09:39:24.10Z"/>
    #        <mediafile duration="156" sageDbId="10490770" startTime="2013-07-15T09:39:24.10Z" type="ImportedVideo">
    #            <segmentList>
    #                <segment duration="156" filePath="T:\The West Wing\Extras\The West Wing Extras Season 07 - Allison Janney Interview.avi" startTime="2013-07-15T09:39:24.10Z"/>
    #            </segmentList>
    #        </mediafile>
    #    </airing>
    #</show>
    
    airing = ""
    mediafile = ""
    segmentList = ""
    segment = ""
    path = ""
    # for each show, make its dir path (if needed) and add the show entry
    for show in STVRoot_sL.findall('show'):
        airing = show.find('airing')
        if airing is not None:
            mediafile = airing.find('mediafile')
            if mediafile is not None:
                segmentList = mediafile.find('segmentList')
                if segmentList is not None:
                    segment = segmentList.find('segment')
                    path = segment.get('filePath')
                    
                    # parse the file path
                    # make me a sub function probably
                    if path is not "":
                        diskLetter = path[0:path.find(":") + 1]
                        
                        diskNode = None
                        for disk in IMT_Root.findall('path'):
                            if disk is not None and disk.get('id') == diskLetter:
                                # use this drive ... do nothing
                                diskNode = disk
                        
                        if diskNode is None:
                            # create the node
                            disk = etree.SubElement(IMT_Root, 'path')
                            disk.set('id',diskLetter)
                            diskNode = disk
                        
                        nodeTmp = diskNode
                        pathTmp = path
                        # this is supposed to find the n'th layer
                        for x in range(0, path.count('\\')):
                            pathTmp = pathTmp[pathTmp.find('\\')+1:]
                            pathIndex = pathTmp.find('\\')
                            if pathIndex < 0:
                                pathIndex = len(pathTmp)
                            dirTmp = pathTmp[:pathIndex]
                            
                            # if the dir does not exist, create it
                            # if the dir does exist, loop
                            nodeTmpTmp = None
                            found = ""
                            for nodeTmpTmp in nodeTmp.findall('path'):
                                if nodeTmpTmp is not None and nodeTmpTmp.get('id') == dirTmp:
                                    nodeTmp = nodeTmpTmp
                                    found = "tr"
                                    break
                            
                            # if it wasn't added, add this node
                            if found == "":
                                nodeTmpTmp = etree.SubElement(nodeTmp, 'path')
                                nodeTmpTmp.set('id', dirTmp)
                                nodeTmpTmp.set('sageDbId', mediafile.get('sageDbId'))
                                nodeTmp = nodeTmpTmp
    
    #"F:\Family Movies\Kids\Vacation - 2012.avi"
    ## LINK TO SHOW INFO http://sagetv.server/sage/DetailedInfo?MediaFileId=10490770
    ## ALSO KNOWN AS PATH + SAGEDBID of the media file
    
    return IMT_Root


def findNode(xmlRoot, Path):
    dprint(__name__, 2, "====== findNode ======: xmlRoot : {0}", Path)
        
    # Get the IP of the SageTV Server
    if g_param['CSettings'].getSetting('ip_sagetv')<>'':
        sagetv_ip = g_param['CSettings'].getSetting('ip_sagetv')
    
    # Get the IP of the SageTV Connect Server
    # -- hopefully this is the same server soon
    if g_param['CSettings'].getSetting('ip_webserver')<>'':
        stv_cnct_ip = g_param['CSettings'].getSetting('ip_webserver')
    
    if g_param['CSettings'].getSetting('sagetv_user')<>'':
        username = g_param['CSettings'].getSetting('sagetv_user')
    
    if g_param['CSettings'].getSetting('sagetv_pass')<>'':
        password = g_param['CSettings'].getSetting('sagetv_pass')
    
    textURL = "/sage/Search?SearchString=&searchType=MediaFiles&Video=on&search_fields=title&filename=&TimeRange=0&Categories=**Any**&Channels=**Any**&watched=any&dontlike=any&favorite=any&firstruns=any&hdtv=any&archived=any&manrec=any&autodelete=any&partials=none&sort1=title_asc&sort2=none&grouping=None&pagelen=100&xml=yes"
    
    textURL = "http://" + username + ":" + password + "@" + sagetv_ip + textURL
    dprint(__name__, 2, "--> {0}", textURL )


    #    if xmlRoot.get('id') is not None:
    #        print "---xmlRoot-->" + xmlRoot.get('id')
    #    else:
    #        print "---xmlRoot--> is None"
    #
    #    print "---Path----->" + Path
    
    for node in xmlRoot.findall('path'):
        #        if node is not None:
        #            print "------id> " + node.get('id')
        #        else:
        #            print "------id> didn't find id"
        
        next = Path.find('/')
        if next >= 0:
            dprint(__name__, 2, "----path> {0}", Path[:Path.find('\\')] )
            if node.get('id') == Path[:Path.find('/')]:
                return findNode( node, Path[Path.find('/') + 1:])
        else:
            dprint(__name__, 2, "----path> {0}", Path )
            if node.get('id') == Path:
                return node
    
    dprint(__name__, 2, "--none--<" )
    
    return None


#
# Generate the XML to display the dir list on screen
# Have it call back with the full path
#
def generatePathXML(path, myList):
    dprint(__name__, 2, "====== generatePathXML ======: myList : {0}", path)
        
    # Get the IP of the SageTV Server
    if g_param['CSettings'].getSetting('ip_sagetv')<>'':
        sagetv_ip = g_param['CSettings'].getSetting('ip_sagetv')
    
    # Get the IP of the SageTV Connect Server
    # -- hopefully this is the same server soon
    if g_param['CSettings'].getSetting('ip_webserver')<>'':
        stv_cnct_ip = g_param['CSettings'].getSetting('ip_webserver')
    
    if g_param['CSettings'].getSetting('sagetv_user')<>'':
        username = g_param['CSettings'].getSetting('sagetv_user')
    
    if g_param['CSettings'].getSetting('sagetv_pass')<>'':
        password = g_param['CSettings'].getSetting('sagetv_pass')


    #<?xml version="1.0" encoding="UTF-8" ?>
    #<atv>
    #    <head>
    #        <script src="{{URL(:/js/utils.js)}}" />
    #        <script src="{{URL(:/js/settings.js)}}" />
    #    </head>
    ATVRoot = etree.Element("atv")
    ATVHead = etree.SubElement(ATVRoot, 'head')
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"https://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/utils.js")
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"https://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/settings.js")
    
    #	<body>
    #		<listWithPreview id="com.sample.list-scroller-split">
    #			<header>
    #				<simpleHeader>
    #					<title>Shows by Name</title>
    #					<subtitle>List all shows by their names</subtitle>
    #				</simpleHeader>
    #			</header>
    ATVBody = etree.SubElement(ATVRoot, 'body')
    ATVListWPreview = etree.SubElement(ATVBody, 'listWithPreview')
    ATVListWPreview.set('id', "Show_List")
    #    ATVListScrollSplit.set('volatile', "true")
    #    ATVListScrollSplit.set('onVolatileReload', "atv.loadAndSwapURL(http://sagetvconnect.server/anything.xml)")
    
    ATV_LSS_Header = etree.SubElement(ATVListWPreview, 'header')
    ATV_LSS_SimpleHeader = etree.SubElement(ATV_LSS_Header, 'simpleHeader')
    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'title')
    ATV_LSS_SH_Title.text = path[path.rfind('/'):]
    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'subtitle')
    ATV_LSS_SH_Title.text = path
    
    
    #    <preview>
    #        <keyedPreview>
    #            <title>&#x00AD;<!--soft-hyphen--></title>
    #            <summary/>
    #            <metadataKeys>
    #                <label>{{TEXT(Version)}}</label>
    #                <label>{{TEXT(Authors)}}</label>
    #                <label>{{TEXT(Wiki/Docs)}}</label>
    #                <label>{{TEXT(Homepage)}}</label>
    #                <label>{{TEXT(Forum)}}</label>
    #            </metadataKeys>
    #            <metadataValues>
    #                <label>Alpha</label>
    #                <label>Baa, roidy</label>
    #                <label>f00b4r</label>
    #                <label>https://github.com/ibaa/plexconnect</label>
    #                <label>http://forums.plexapp.com/index.php/forum/136-appletv-plexconnect/</label>
    #            </metadataValues>
    #            <image>{{URL(:/thumbnails/PlexConnectLogo.jpg)}}</image>
    #        </keyedPreview>
    #    </preview>
    #
    #    ATV_LSS_Header = etree.SubElement(ATVListWPreview, 'preview')
    #    ATV_LSS_SimpleHeader = etree.SubElement(ATV_LSS_Header, 'keyedPreview')
    #    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'title')
    #    ATV_LSS_SH_Title.text = "&#x00AD;<!--soft-hyphen-->"
    #    etree.SubElement(ATV_LSS_SimpleHeader, 'summary')
    #    etree.SubElement(ATV_LSS_SimpleHeader, 'metadataKeys')
    #    etree.SubElement(ATV_LSS_SimpleHeader, 'metadataValues')
    #    ATV_LSS_SH_Image = etree.SubElement(ATV_LSS_SimpleHeader, 'image')
    #    ATV_LSS_SH_Image.text = "http://sagetv.server/sagem/m/images/SageLogo256.png"
    
    
    
    #<menu>
    #    <sections>
    #        <menuSection>
    ATV_LSS_Menu = etree.SubElement(ATVListWPreview, 'menu')
    ATV_LSS_Sections = etree.SubElement(ATV_LSS_Menu, 'sections')
    ATV_LSS_MenuSections = etree.SubElement(ATV_LSS_Sections, 'menuSection')
    
    #           <items>
    ATV_LSS_MS_Items = etree.SubElement(ATV_LSS_MenuSections, 'items')
    

    count = 0

    myStringList = []
    for myItem in myList:
        myStringList.append( myItem.get('id'))
    
    mySortedList = sorted(myStringList)
    # Make and return menu Screen XML and
    for myItem in mySortedList:
        count = count + 1
    
        # here is the part that repeats for each show
        #            <oneLineMenuItem id="list_1">
        #                <label>Action</label>
        #                <accessories>
        #                    <arrow/>
        #                    <unplayedDot/>
        #                    <partiallyPlayedDot/>
        #                </accessories>
        #            </oneLineMenuItem>
        #        href = "http://sagetvconnect.server/mediaPath.xml="
        href = ""
        if path <> "":
            href = path + '/'
        href = href + myItem
        href = href.replace(' ', '*')
        href = href.replace('\'', '&apos;')

        href = "atv.loadURL('http://" + stv_cnct_ip + "/mediaPath.xml=" + href + "')"
        dprint(__name__, 2, "href --> {0}", href)

        ATV_LSS_MS_MenuItem = etree.SubElement(ATV_LSS_MS_Items, 'oneLineMenuItem')
        ATV_LSS_MS_MenuItem.set("id", "list_" + str(count) )
        ATV_LSS_MS_MenuItem.set("onSelect", href )
        ATV_LSS_MS_MenuItemLabel = etree.SubElement(ATV_LSS_MS_MenuItem, 'label')
        ATV_LSS_MS_MenuItemLabel.text = myItem
        ATV_LSS_MS_MI_A = etree.SubElement(ATV_LSS_MS_MenuItem, 'accessories')
        etree.SubElement(ATV_LSS_MS_MI_A, 'arrow')


    return ATVRoot




def makeDirList(path):
    dprint(__name__, 2, "====== makeDirList ======: {0}", path)
        
    # Get the IP of the SageTV Server
    if g_param['CSettings'].getSetting('ip_sagetv')<>'':
        sagetv_ip = g_param['CSettings'].getSetting('ip_sagetv')
    
    # Get the IP of the SageTV Connect Server
    # -- hopefully this is the same server soon
    if g_param['CSettings'].getSetting('ip_webserver')<>'':
        stv_cnct_ip = g_param['CSettings'].getSetting('ip_webserver')
    
    if g_param['CSettings'].getSetting('sagetv_user')<>'':
        username = g_param['CSettings'].getSetting('sagetv_user')
    
    if g_param['CSettings'].getSetting('sagetv_pass')<>'':
        password = g_param['CSettings'].getSetting('sagetv_pass')


    filename = 'dirList.xml'
    # see if the directory listing file exists

    # if the directory listing file does not exist
    if not os.path.isfile(filename):
        # update to rebuild this every week?
        # on demand?  Maybe have a menu item?
        # create it
        XML = makeDirTree()

#        XML.write(filename)
        file = codecs.open(filename, "w", "utf-8")
#        file.write()
#        file.write(XML_prettystring(XML))
        xmlstring = etree.tostring(XML)
        xmlstring = xmlstring.replace( '\'', '&apos;')

        file.write(xmlstring)
        file.close()

    
    tree = etree.parse(filename)
    dirRoot = tree.getroot()
    
    #    print "--tag---> " + dirRoot.tag
    #    if dirRoot.get('id') is not None:
    #        print "--id----> " + dirRoot.find('id')

    if path == "":
        myNode = dirRoot
    else:
        path = path.strip('\\')
        path = path.strip('/')
        myNode = findNode(dirRoot, path)

    if myNode is None:
        # return error
        dprint(__name__, 2, "Error: makeDirList() - No XML found to process")
        return XML_Error("makeDirList", "No XML found to process ")

    
    # get all items at that level
    myList = myNode.findall('path')
    
    # if there is nothing in my list, than a file was selected, access its sagedbid
    if len(myList) == 0:
        # Make and return item Screen XML and
        ## LINK TO SHOW INFO http://sagetv.server/sage/DetailedInfo?MediaFileId=10490770
        
        print "--id -------> " + myNode.get('id')
        if myNode.get('sageDbId') is not None:
            dprint(__name__, 2, "--sageDbId -> {0}", myNode.get('sageDbId'))
            txtTmp = "/MediaId=" + myNode.get('sageDbId')

            return makeMediaInfo(txtTmp)
        else:
            return XML_Error("makeDirList", "Unable to make MediaInfo Screen. There is no MediaFileId entry")


    else:
        return generatePathXML(path, myList)

    return XML_Error("makeDirList", "Failed to process")


# for each command {{cmd}} do what it says
def XML_ExpandNode(elem, child, src, srcXML, text_tail):
    if text_tail=='TEXT':  # read line from text or tail
        line = child.text
    elif text_tail=='TAIL':
        line = child.tail
    else:
        dprint(__name__, 0, "XML_ExpandNode - text_tail badly specified: {0}", text_tail)
        return False
    
    pos = 0
    while line!=None:
        cmd_start = line.find('{{',pos)
        cmd_end   = line.find('}}',pos)
        if cmd_start==-1 or cmd_end==-1 or cmd_start>cmd_end:
            return False  # tree not touched, line unchanged
        
        dprint(__name__, 2, "XML_ExpandNode: {0}", line)
        
        cmd = line[cmd_start+2:cmd_end]
        if cmd[-1]!=')':
            dprint(__name__, 0, "XML_ExpandNode - closing bracket missing: {0} ", line)
        
        parts = cmd.split('(',1)
        cmd = parts[0]
        param = parts[1].strip(')')  # remove ending bracket
        
        res = False
        if hasattr(CCommandCollection, 'TREE_'+cmd):  # expand tree, work COPY, CUT
            line = line[:cmd_start] + line[cmd_end+2:]  # remove cmd from text and tail
            if text_tail=='TEXT':  
                child.text = line
            elif text_tail=='TAIL':
                child.tail = line
            
            try:
                res = getattr(g_CommandCollection, 'TREE_'+cmd)(elem, child, src, srcXML, param)
            except:
                dprint(__name__, 0, "XML_ExpandNode - Error in cmd {0}, line {1}\n{2}", cmd, line, traceback.format_exc())
            
            if res==True:
                return True  # tree modified, node added/removed: restart from 1st elem
        
        elif hasattr(CCommandCollection, 'ATTRIB_'+cmd):  # check other known cmds: VAL, EVAL...
            dprint(__name__, 2, "XML_ExpandNode - Stumbled over {0} in line {1}", cmd, line)
            pos = cmd_end
        else:
            dprint(__name__, 0, "XML_ExpandNode - Found unknown cmd {0} in line {1}", cmd, line)
            line = line[:cmd_start] + "((UNKNOWN:"+cmd+"))" + line[cmd_end+2:]  # mark unknown cmd in text or tail
            if text_tail=='TEXT':
                child.text = line
            elif text_tail=='TAIL':
                child.tail = line
    
    dprint(__name__, 2, "XML_ExpandNode: {0} - done", line)
    return False



def XML_ExpandAllAttrib(elem, src, srcXML):
    # unpack template commands in elem.text
    line = elem.text
    if line!=None:
        elem.text = XML_ExpandLine(src, srcXML, line.strip())
    
    # unpack template commands in elem.tail
    line = elem.tail
    if line!=None:
        elem.tail = XML_ExpandLine(src, srcXML, line.strip())
    
    # unpack template commands in elem.attrib.value
    for attrib in elem.attrib:
        line = elem.get(attrib)
        elem.set(attrib, XML_ExpandLine(src, srcXML, line.strip()))
    
    # recurse into children
    for el in elem:
        XML_ExpandAllAttrib(el, src, srcXML)



def XML_ExpandLine(src, srcXML, line):
    pos = 0
    while True:
        cmd_start = line.find('{{',pos)
        cmd_end   = line.find('}}',pos)
        if cmd_start==-1 or cmd_end==-1 or cmd_start>cmd_end:
            break;
        
        dprint(__name__, 2, "XML_ExpandLine: {0}", line)
        
        cmd = line[cmd_start+2:cmd_end]
        if cmd[-1]!=')':
            dprint(__name__, 0, "XML_ExpandLine - closing bracket missing: {0} ", line)
        
        parts = cmd.split('(',1)
        cmd = parts[0]
        param = parts[1][:-1]  # remove ending bracket
        
        if hasattr(CCommandCollection, 'ATTRIB_'+cmd):  # expand line, work VAL, EVAL...
            
            try:
                res = getattr(g_CommandCollection, 'ATTRIB_'+cmd)(src, srcXML, param)
                line = line[:cmd_start] + res + line[cmd_end+2:]
                pos = cmd_start+len(res)
            except:
                dprint(__name__, 0, "XML_ExpandLine - Error in {0}\n{1}", line, traceback.format_exc())
                line = line[:cmd_start] + "((ERROR:"+cmd+"))" + line[cmd_end+2:]
        
        elif hasattr(CCommandCollection, 'TREE_'+cmd):  # check other known cmds: COPY, CUT
            dprint(__name__, 2, "XML_ExpandLine - stumbled over {0} in line {1}", cmd, line)
            pos = cmd_end
        else:
            dprint(__name__, 0, "XML_ExpandLine - Found unknown cmd {0} in line {1}", cmd, line)
            line = line[:cmd_start] + "((UNKNOWN:"+cmd+"))" + line[cmd_end+2:]    
        
        dprint(__name__, 2, "XML_ExpandLine: {0} - done", line)
    return line

"""
# PlexAPI
"""
def PlexAPI_getTranscodePath(options, path):
    UDID = options['PlexConnectUDID']
    transcodePath = '/video/:/transcode/universal/start.m3u8?'
    
    quality = { '480p 2.0Mbps' :('720x480', '60', '2000'), \
                '720p 3.0Mbps' :('1280x720', '75', '3000'), \
                '720p 4.0Mbps' :('1280x720', '100', '4000'), \
                '1080p 8.0Mbps' :('1920x1080', '60', '8000'), \
                '1080p 10.0Mbps' :('1920x1080', '75', '10000'), \
                '1080p 12.0Mbps' :('1920x1080', '90', '12000'), \
                '1080p 20.0Mbps' :('1920x1080', '100', '20000'), \
                '1080p 40.0Mbps' :('1920x1080', '100', '40000') }
    setQuality = g_ATVSettings.getSetting(UDID, 'transcodequality')
    vRes = quality[setQuality][0]
    vQ = quality[setQuality][1]
    mVB = quality[setQuality][2]
    dprint(__name__, 1, "Setting transcode quality Res:{0} Q:{1} {2}Mbps", vRes, vQ, mVB)
    sS = g_ATVSettings.getSetting(UDID, 'subtitlesize')
    dprint(__name__, 1, "Subtitle size: {0}", sS)
    aB = g_ATVSettings.getSetting(UDID, 'audioboost')
    dprint(__name__, 1, "Audio Boost: {0}", aB)
    
    args = dict()
    args['session'] = UDID
    args['protocol'] = 'hls'
    args['videoResolution'] = vRes
    args['maxVideoBitrate'] = mVB
    args['videoQuality'] = vQ
    args['directStream'] = '1'
    args['directPlay'] = '0'
    args['subtitleSize'] = sS
    args['audioBoost'] = aB
    args['fastSeek'] = '1'
    args['path'] = path
    
    xargs = PlexAPI_getXArgs(options)
    
    return transcodePath + urlencode(args) + '&' + urlencode(xargs)

def PlexAPI_getXArgs(options=None):
    xargs = dict()
    xargs['X-Plex-Device'] = 'AppleTV'
    xargs['X-Plex-Model'] = '3,1' # Base it on AppleTV model.
    if not options is None:
        if 'PlexConnectATVName' in options:
            xargs['X-Plex-Device-Name'] = options['PlexConnectATVName'] # "friendly" name: aTV-Settings->General->Name.
    xargs['X-Plex-Platform'] = 'iOS'
    xargs['X-Plex-Client-Platform'] = 'iOS'
    xargs['X-Plex-Platform-Version'] = '5.3' # Base it on AppleTV OS version.
    xargs['X-Plex-Product'] = 'PlexConnect'
    xargs['X-Plex-Version'] = '0.2'
    
    xargs['X-Plex-Client-Capabilities'] = "protocols=http-live-streaming,http-mp4-streaming,http-streaming-video,http-streaming-video-720p,http-mp4-video,http-mp4-video-720p;videoDecoders=h264{profile:high&resolution:1080&level:41};audioDecoders=mp3,aac{bitrate:160000}"
    
    return xargs



"""
# Command expander classes
# CCommandHelper():
#     base class to the following, provides basic parsing & evaluation functions
# CCommandCollection():
#     cmds to set up sources (ADDXML, VAR)
#     cmds with effect on the tree structure (COPY, CUT) - must be expanded first
#     cmds dealing with single node keys, text, tail only (VAL, EVAL, ADDR_PMS ,...)
"""
class CCommandHelper():
    def __init__(self, options, PMSroot, path):
        self.options = options
        self.PMSroot = {'main': PMSroot}
        self.path = {'main': path}
        self.variables = {}
    
    # internal helper functions
    def getParam(self, src, param):
        parts = param.split(':',1)
        param = parts[0]
        leftover=''
        if len(parts)>1:
            leftover = parts[1]
        
        param = param.replace('&col;',':')  # colon  # replace XML_template special chars
        param = param.replace('&ocb;','{')  # opening curly brace
        param = param.replace('&ccb;','}')  # closinging curly brace
        
        param = param.replace('&quot;','"')  # replace XML special chars
        param = param.replace('&apos;',"'")
        param = param.replace('&lt;','<')
        param = param.replace('&gt;','>')
        param = param.replace('&amp;','&')  # must be last
        
        dprint(__name__, 2, "CCmds_getParam: {0}, {1}", param, leftover)
        return [param, leftover]
    
    def getKey(self, src, srcXML, param):
        attrib, leftover = self.getParam(src, param)
        default, leftover = self.getParam(src, leftover)
        
        el, srcXML, attrib = self.getBase(src, srcXML, attrib)         
        
        UDID = self.options['PlexConnectUDID']
        # walk the path if neccessary
        while '/' in attrib and el!=None:
            parts = attrib.split('/',1)
            if parts[0].startswith('#'):  # internal variable in path
                el = el.find(self.variables[parts[0][1:]])
            elif parts[0].startswith('$'):  # setting
                el = el.find(g_ATVSettings.getSetting(UDID, parts[0][1:]))
            else:
                el = el.find(parts[0])
            attrib = parts[1]
        
        # check element and get attribute
        if attrib.startswith('#'):  # internal variable
            res = self.variables[attrib[1:]]
            dfltd = False
        elif attrib.startswith('$'):  # setting
            res = g_ATVSettings.getSetting(UDID, attrib[1:])
            dfltd = False
        elif el!=None and attrib in el.attrib:
            res = el.get(attrib)
            dfltd = False
        
        else:  # path/attribute not found
            res = default
            dfltd = True
        
        dprint(__name__, 2, "CCmds_getKey: {0},{1},{2}", res, leftover,dfltd)
        return [res,leftover,dfltd]
    
    def getElement(self, src, srcXML, param):
        tag, leftover = self.getParam(src, param)
        
        el, srcXML, tag = self.getBase(src, srcXML, tag)
        
        # walk the path if neccessary
        while True:
            parts = tag.split('/',1)
            el = el.find(parts[0])
            if not '/' in tag or el==None:
                break
            tag = parts[1]
        return [el, leftover]
    
    def getBase(self, src, srcXML, param):
        # get base element
        if param.startswith('@'):  # redirect to additional XML
            parts = param.split('/',1)
            srcXML = parts[0][1:]
            src = self.PMSroot[srcXML]
            leftover=''
            if len(parts)>1:
                leftover = parts[1]
        elif param.startswith('/'):  # start at root
            src = self.PMSroot['main']
            leftover = param[1:]
        else:
            leftover = param
        
        return [src, srcXML, leftover]
    
    def getConversion(self, src, param):
        conv, leftover = self.getParam(src, param)
        
        # build conversion "dictionary"
        convlist = []
        if conv!='':
            parts = conv.split('|')
            for part in parts:
                convstr = part.split('=')
                convlist.append((convstr[0], convstr[1]))
        
        dprint(__name__, 2, "CCmds_getConversion: {0},{1}", convlist, leftover)
        return [convlist, leftover]
    
    def applyConversion(self, val, convlist):
        # apply string conversion            
        if convlist!=[]:
            for part in reversed(sorted(convlist)):
                if val>=part[0]:
                    val = part[1]
                    break
        
        dprint(__name__, 2, "CCmds_applyConversion: {0}", val)
        return val
    
    def applyMath(self, val, math, frmt):
        # apply math function - eval
        try:
            x = eval(val)
            if math!='':
                x = eval(math)
            val = ('{0'+frmt+'}').format(x)
        except:
            dprint(__name__, 0, "CCmds_applyMath: Error in math {0}, frmt {1}\n{2}", math, frmt, traceback.format_exc())
        # apply format specifier
        
        dprint(__name__, 2, "CCmds_applyMath: {0}", val)
        return val
    
    def _(self, msgid):
        return Localize.getTranslation(self.options['aTVLanguage']).ugettext(msgid)



class CCommandCollection(CCommandHelper):
    # XML TREE modifier commands
    # add new commands to this list!
    def TREE_COPY(self, elem, child, src, srcXML, param):
        tag, param_enbl = self.getParam(src, param)

        src, srcXML, tag = self.getBase(src, srcXML, tag)        
        
        # walk the src path if neccessary
        while '/' in tag and src!=None:
            parts = tag.split('/',1)
            src = src.find(parts[0])
            tag = parts[1]
        
        childToCopy = child
        elem.remove(child)
        
        # duplicate child and add to tree
        for elemSRC in src.findall(tag):
            key = 'COPY'
            if param_enbl!='':
                key, leftover, dfltd = self.getKey(elemSRC, srcXML, param_enbl)
                conv, leftover = self.getConversion(elemSRC, leftover)
                if not dfltd:
                    key = self.applyConversion(key, conv)
            
            if key:
                el = copy.deepcopy(childToCopy)
                XML_ExpandTree(el, elemSRC, srcXML)
                XML_ExpandAllAttrib(el, elemSRC, srcXML)
                
                if el.tag=='__COPY__':
                    for child in list(el):
                        elem.append(child)
                else:
                    elem.append(el)
            
        return True  # tree modified, nodes updated: restart from 1st elem
    
    def TREE_CUT(self, elem, child, src, srcXML, param):
        key, leftover, dfltd = self.getKey(src, srcXML, param)
        conv, leftover = self.getConversion(src, leftover)
        if not dfltd:
            key = self.applyConversion(key, conv)
        if key:
            elem.remove(child)
            return True  # tree modified, node removed: restart from 1st elem
        else:
            return False  # tree unchanged
    
    def TREE_ADDXML(self, elem, child, src, srcXML, param):
        tag, leftover = self.getParam(src, param)
        key, leftover, dfltd = self.getKey(src, srcXML, leftover)
        
        if key.startswith('/'):  # internal full path.
            path = key
        #elif key.startswith('http://'):  # external address
        #    path = key
        #    hijack = g_param['HostToIntercept']
        #    if hijack in path:
        #        dprint(__name__, 1, "twisting...")
        #        hijack_twisted = hijack[::-1]
        #        path = path.replace(hijack, hijack_twisted)
        #        dprint(__name__, 1, path)
        elif key == '':  # internal path
            path = self.path[srcXML]
        else:  # internal path, add-on
            path = self.path[srcXML] + '/' + key
        
        PMS = XML_ReadFromURL(g_param['Addr_PMS'], path)
        self.PMSroot[tag] = PMS.getroot()  # store additional PMS XML
        self.path[tag] = path  # store base path
        
        return False  # tree unchanged (well, source tree yes. but that doesn't count...)
    
    def TREE_VAR(self, elem, child, src, srcXML, param):
        var, leftover = self.getParam(src, param)
        key, leftover, dfltd = self.getKey(src, srcXML, leftover)
        conv, leftover = self.getConversion(src, leftover)
        if not dfltd:
            key = self.applyConversion(key, conv)
        
        self.variables[var] = key
        return False  # tree unchanged
    
    
    # XML ATTRIB modifier commands
    # add new commands to this list!
    def ATTRIB_VAL(self, src, srcXML, param):
        key, leftover, dfltd = self.getKey(src, srcXML, param)
        conv, leftover = self.getConversion(src, leftover)
        if not dfltd:
            key = self.applyConversion(key, conv)
        return key
    
    def ATTRIB_EVAL(self, src, srcXML, param):
        key, leftover, dfltd = self.getKey(src, srcXML, param)
        math, leftover = self.getParam(src, leftover)
        frmt, leftover = self.getParam(src, leftover)
        if not dfltd:
            key = self.applyMath(key, math, frmt)
        return key
    
    def ATTRIB_SETTING(self, src, srcXML, param):
        opt, leftover = self.getParam(src, param)
        UDID = self.options['PlexConnectUDID']
        return g_ATVSettings.getSetting(UDID, opt)
    
    def ATTRIB_ADDPATH(self, src, srcXML, param):
        addpath, leftover, dfltd = self.getKey(src, srcXML, param)
        if addpath.startswith('/'):
            res = addpath
        elif addpath == '':
            res = self.path[srcXML]
        else:
            res = self.path[srcXML]+'/'+addpath
        return res

    def ATTRIB_BIGIMAGEURL(self, src, srcXML, param):
        key, leftover, dfltd = self.getKey(src, srcXML, param)
        return self.imageUrl(self.path[srcXML], key, 768, 768)
    
    def ATTRIB_IMAGEURL(self, src, srcXML, param):
        key, leftover, dfltd = self.getKey(src, srcXML, param)
        return self.imageUrl(self.path[srcXML], key, 384, 384)
            
    def imageUrl(self, path, key, width, height):
        if key.startswith('/'):  # internal full path.
            res = 'http://127.0.0.1:32400' + key
        elif key.startswith('http://'):  # external address
            res = key
            hijack = g_param['HostToIntercept']
            if hijack in res:
                dprint(__name__, 1, "twisting...")
                hijack_twisted = hijack[::-1]
                res = res.replace(hijack, hijack_twisted)
                dprint(__name__, 1, res)
        else:
            res = 'http://127.0.0.1:32400' + path + '/' + key
        
        # This is bogus (note the extra path component) but ATV is stupid when it comes to caching images, it doesn't use querystrings.
        # Fortunately PMS is lenient...
        #
        return 'http://' + g_param['Addr_PMS'] + '/photo/:/transcode/%s/?width=%d&height=%d&url=' % (quote_plus(res), width, height) + quote_plus(res)
            
    def ATTRIB_URL(self, src, srcXML, param):
        key, leftover, dfltd = self.getKey(src, srcXML, param)
        if key.startswith('/'):  # internal full path.
            res = 'http://' + g_param['HostOfPlexConnect'] + key
        elif key.startswith('http://'):  # external address
            res = key
            hijack = g_param['HostToIntercept']
            if hijack in res:
                dprint(__name__, 1, "twisting...")
                hijack_twisted = hijack[::-1]
                res = res.replace(hijack, hijack_twisted)
                dprint(__name__, 1, res)
        elif key == '':  # internal path
            res = 'http://' + g_param['HostOfPlexConnect'] + self.path[srcXML]
        else:  # internal path, add-on
            res = 'http://' + g_param['HostOfPlexConnect'] + self.path[srcXML] + '/' + key
        return res
    
    def ATTRIB_MEDIAURL(self, src, srcXML, param):
        Video, leftover = self.getElement(src, srcXML, param)
        
        if Video!=None:
            Media = Video.find('Media')
        
        # check "Media" element and get key
        if Media!=None:
            UDID = self.options['PlexConnectUDID']
            
            if g_ATVSettings.getSetting(UDID, 'forcedirectplay')=='True' \
               or \
               g_ATVSettings.getSetting(UDID, 'forcetranscode')!='True' and \
               Media.get('protocol','-') in ("hls") \
               or \
               g_ATVSettings.getSetting(UDID, 'forcetranscode')!='True' and \
               Media.get('container','-') in ("mov", "mp4") and \
               Media.get('videoCodec','-') in ("mpeg4", "h264", "drmi") and \
               Media.get('audioCodec','-') in ("aac", "ac3", "drms"):
                # direct play for...
                #    force direct play
                # or HTTP live stream
                # or native aTV media
                res, leftover, dfltd = self.getKey(Media, srcXML, 'Part/key')
                
                if Media.get('indirect',None):  # indirect... todo: select suitable resolution, today we just take first Media
                    key, leftover, dfltd = self.getKey(Media, srcXML, 'Part/key')
                    PMS = XML_ReadFromURL(g_param['Addr_PMS'], key)  # todo... check key for trailing '/' or even 'http'
                    res, leftover, dfltd = self.getKey(PMS.getroot(), srcXML, 'Video/Media/Part/key')
                
            else:
                # request transcoding
                res = Video.get('key','')
                res = PlexAPI_getTranscodePath(self.options, res)
        else:
            dprint(__name__, 0, "MEDIAPATH - element not found: {0}", param)
            res = 'FILE_NOT_FOUND'  # not found?
        
        if res.startswith('/'):  # internal full path.
            res = 'http://' + g_param['Addr_PMS'] + res
        elif res.startswith('http://'):  # external address
            hijack = g_param['HostToIntercept']
            if hijack in res:
                dprint(__name__, 1, "twisting...")
                hijack_twisted = hijack[::-1]
                res = res.replace(hijack, hijack_twisted)
                dprint(__name__, 1, res)
        else:  # internal path, add-on
            res = 'http://' + g_param['Addr_PMS'] + self.path[srcXML] + res
        return res
            
    def ATTRIB_ADDR_PMS(self, src, srcXML, param):
        return g_param['Addr_PMS']
    
    def ATTRIB_episodestring(self, src, srcXML, param):
        parentIndex, leftover, dfltd = self.getKey(src, srcXML, param)  # getKey "defaults" if nothing found.
        index, leftover, dfltd = self.getKey(src, srcXML, leftover)
        title, leftover, dfltd = self.getKey(src, srcXML, leftover)
        out = self._("{0:0d}x{1:02d} {2}").format(int(parentIndex), int(index), title)
        return out
    
    def ATTRIB_sendToATV(self, src, srcXML, param):
        ratingKey, leftover, dfltd = self.getKey(src, srcXML, param)  # getKey "defaults" if nothing found.
        duration, leftover, dfltd = self.getKey(src, srcXML, leftover)
        UDID = self.options['PlexConnectUDID']
        out = "atv.sessionStorage['ratingKey']='" + ratingKey + "';atv.sessionStorage['duration']='" + duration + "';" + \
              "atv.sessionStorage['showplayerclock']='" + g_ATVSettings.getSetting(UDID, 'showplayerclock') + "';" + \
              "atv.sessionStorage['showendtime']='" + g_ATVSettings.getSetting(UDID, 'showendtime') + "';" + \
              "atv.sessionStorage['overscanadjust']='" + g_ATVSettings.getSetting(UDID, 'overscanadjust') + "';" + \
              "atv.sessionStorage['clockposition']='" + g_ATVSettings.getSetting(UDID, 'clockposition') + "';" + \
              "atv.sessionStorage['timeformat']='" + g_ATVSettings.getSetting(UDID, 'timeformat') + "';"
        return out 
    
    def ATTRIB_getDurationString(self, src, srcXML, param):
        duration, leftover, dfltd = self.getKey(src, srcXML, param)
        min = int(duration)/1000/60
        UDID = self.options['PlexConnectUDID']
        if g_ATVSettings.getSetting(UDID, 'durationformat') == 'Minutes':
            return self._("{0:d} Minutes").format(min)
        else:
            if len(duration) > 0:
                hour = min/60
                min = min%60
                if hour == 0: return self._("{0:d} Minutes").format(min)
                else: return self._("{0:d}hr {1:d}min").format(hour, min)
        return ""
    
    def ATTRIB_contentRating(self, src, srcXML, param):
        rating, leftover, dfltd = self.getKey(src, srcXML, param)
        if rating.find('/') != -1:
            parts = rating.split('/')
            return parts[1]
        else:
            return rating
        
    def ATTRIB_unwatchedCountGrid(self, src, srcXML, param):
        total, leftover, dfltd = self.getKey(src, srcXML, param)
        viewed, leftover, dfltd = self.getKey(src, srcXML, leftover)
        unwatched = int(total) - int(viewed)
        return str(unwatched)
    
    def ATTRIB_unwatchedCountList(self, src, srcXML, param):
        total, leftover, dfltd = self.getKey(src, srcXML, param)
        viewed, leftover, dfltd = self.getKey(src, srcXML, leftover)
        unwatched = int(total) - int(viewed)
        if unwatched > 0: return self._("{0} unwatched").format(unwatched)
        else: return ""
    
    def ATTRIB_TEXT(self, src, srcXML, param):
        return self._(param)
    
    def ATTRIB_PMSCOUNT(self, src, srcXML, param):
        return str(len(g_param['PMS_list']))
    
    def ATTRIB_PMSNAME(self, src, srcXML, param):
        UDID = self.options['PlexConnectUDID']
        PMS_list = g_param['PMS_list']
        PMS_uuid = g_ATVSettings.getSetting(UDID, 'pms_uuid')
        
        if len(PMS_list)==0:
            return "[no Server in Proximity]"
        else:
            PMS_uuid = g_ATVSettings.getSetting(self.options['PlexConnectUDID'], 'pms_uuid')
            if PMS_uuid in PMS_list:
                return PMS_list[PMS_uuid]['serverName'].decode('utf-8', 'replace')  # return as utf-8
            else:
                return '[PMS_uuid not found]'



if __name__=="__main__":
    cfg = Settings.CSettings()
    param = {}
    param['CSettings'] = cfg
    
    param['Addr_PMS'] = '*Addr_PMS*'
    param['HostToIntercept'] = 'trailers.apple.com'
    setParams(param)
    
    cfg = ATVSettings.CATVSettings()
    setATVSettings(cfg)
    
    print "load PMS XML"
    _XML = '<PMS number="1" string="Hello"> \
                <DATA number="42" string="World"></DATA> \
                <DATA string="Sun"></DATA> \
            </PMS>'
    PMSroot = etree.fromstring(_XML)
    PMSTree = etree.ElementTree(PMSroot)
    XML_prettyprint(PMSTree)
    
    print
    print "load aTV XML template"
    _XML = '<aTV> \
                <INFO num="{{VAL(number)}}" str="{{VAL(string)}}">Info</INFO> \
                <FILE str="{{VAL(string)}}" strconv="{{VAL(string::World=big|Moon=small|Sun=huge)}}" num="{{VAL(number:5)}}" numfunc="{{EVAL(number:5:int(x/10):&amp;col;02d)}}"> \
                    File{{COPY(DATA)}} \
                </FILE> \
                <PATH path="{{ADDPATH(file:unknown)}}" /> \
                <accessories> \
                    <cut />{{CUT(number::0=cut|1=)}} \
                    <dontcut />{{CUT(attribnotfound)}} \
                </accessories> \
                <ADDPATH>{{ADDPATH(string)}}</ADDPATH> \
                <ADDR_PMS>{{ADDR_PMS()}}</ADDR_PMS> \
                <COPY2>={{COPY(DATA)}}=</COPY2> \
            </aTV>'
    aTVroot = etree.fromstring(_XML)
    aTVTree = etree.ElementTree(aTVroot)
    XML_prettyprint(aTVTree)
    
    print
    print "unpack PlexConnect COPY/CUT commands"
    options = {}
    options['PlexConnectUDID'] = '007'
    g_CommandCollection = CCommandCollection(options, PMSroot, '/library/sections/')
    XML_ExpandTree(aTVroot, PMSroot, 'main')
    XML_ExpandAllAttrib(aTVroot, PMSroot, 'main')
    del g_CommandCollection
    
    print
    print "resulting aTV XML"
    XML_prettyprint(aTVTree)
    
    print
    #print "store aTV XML"
    #str = XML_prettystring(aTVTree)
    #f=open(sys.path[0]+'/XML/aTV_fromTmpl.xml', 'w')
    #f.write(str)
    #f.close()
    
    del cfg
