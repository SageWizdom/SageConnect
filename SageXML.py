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
from urllib import unquote_plus

import Settings, ATVSettings
#import PlexAPI
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
    indent(XML)
    XML.write(sys.stdout)

def XML_prettystring(XML):
    indent(XML)
    return(etree.tostring(XML))



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



"""
# GetURL
# Source (somewhat): https://github.com/hippojay/plugin.video.plexbmc
# attempted to adjust to use "requests" library to support authentication
"""
def GetURL(address, path):
    try:
        conn = httplib.HTTPConnection(address, timeout=10)


        if param['CSettings'].getSetting('sagetv_user')<>'':
            username = param['CSettings'].getSetting('sagetv_user')

        if param['CSettings'].getSetting('sagetv_pass')<>'':
            password = param['CSettings'].getSetting('sagetv_pass')
        
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
    dprint(__name__, 1, "XML_ReadFromURL {0}:{1}", address, path)

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




# makeTopMenu()
#    SageTV -> nothing
#    makeTitleGrid(path)
#       makeShowList(path)
#           makeMediaInfo(path)
#               makePlay(path)
#    makeDirList(path[path.find('=')+1:])
#       generatePathXML(path, myList)
#       makePlay(path)
#    searchTitle()
#       searchMedia(path)
#           makePlay(path)

'''

 This function creates the top level "trailers" menu.
 It does not read from any external systems.

'''
def makeTopMenu():
    dprint(__name__, 1, "====== makeTopMenu ======" )
    InitCfg()

    # Get the IP of the SageTV Server
    if g_param['CSettings'].getSetting('ip_sagetv')<>'':
        sagetv_ip = g_param['CSettings'].getSetting('ip_sagetv')

    # Get the IP of the SageTV Connect Server
    # -- hopefully this is the same server soon
    if g_param['CSettings'].getSetting('ip_webserver')<>'':
        stv_cnct_ip = g_param['CSettings'].getSetting('ip_webserver')
    
    #<atv>
    #    <head>
    #        <script src="{{URL(:/js/utils.js)}}" />
    #    </head>
    ATVRoot = etree.Element("atv")
    ATVHead = etree.SubElement(ATVRoot, 'head')
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"http://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/utils.js")


    #	<body>
    #		<listScrollerSplit id="com.sample.list-scroller-split">
    ATVBody = etree.SubElement(ATVRoot, 'body')

#    ATVLSS = etree.SubElement(ATVBody, 'optionDialog') # Centered and Centered!
#    ATVLSS.set('id', "com.sample.movie-grid")


    ATVLSS = etree.SubElement(ATVBody, 'listScrollerSplit') # Centered and Centered!
    ATVLSS.set('id', "com.menu.Main.list-scroller-split")
##    ATVListWPreview.set('volatile', "true")
##    ATVListWPreview.set('onVolatileReload', "atv.loadAndSwapURL('http://" + stv_cnct_ip  + "/SageConnect.xml')")


    #        <menu>
    #            <sections>
    #                <menuSection>
    #                   <items>
    ATV_LSS_Menu = etree.SubElement(ATVLSS, 'menu')
    ATV_LSS_Sections = etree.SubElement(ATV_LSS_Menu, 'sections')
    ATV_LSS_MenuSections = etree.SubElement(ATV_LSS_Sections, 'menuSection')


    ATV_LSS_MS_Items = etree.SubElement(ATV_LSS_MenuSections, 'items')

    # Repeat for each item in the list
    #<items>
    #    <twoLineEnhancedMenuItem id="1a"
    #        onPlay="atv.loadURL('http://SageConnect.Server/exampleLayouts=scroller.xml')"
    #        onSelect="atv.loadURL('http://SageConnect.Server/exampleLayouts=scroller.xml')">
    #        <label>TV</label>
    #        <label2>Recorded Television</label2>
    #        <image>http://SageConnect.Server/thumbnails/TvIcon.png</image>
    #        <!--<defaultImage>resource://Poster.png</defaultImage>-->
    #        <preview>
    #            <keyedPreview>
    #                <title>Recorded Television</title>
    #                <summary>27 Shows (285 Recordings)</summary>
    #                <image>http://SageConnect.Server/thumbnails/SageTVLogo.jpg</image>
    #            </keyedPreview>
    #        </preview>
    #    </twoLineEnhancedMenuItem>
    #</items>


    #
    # Add Generic SageTV item.... use this to show current status
    #
    label = "SageTV"
    ATV_LSS_MS_I_Item = etree.SubElement(ATV_LSS_MS_Items, 'twoLineEnhancedMenuItem')
    ATV_LSS_MS_I_Item.set("id", label )
    ATV_LSS_MS_I_ItemLabel = etree.SubElement(ATV_LSS_MS_I_Item, 'label')
    ATV_LSS_MS_I_ItemLabel.text = label
    ATV_LSS_MS_I_ItemImg = etree.SubElement(ATV_LSS_MS_I_Item, 'image')
    ATV_LSS_MS_I_ItemImg.text = "http://" + stv_cnct_ip + "/thumbnails/Ball.png"
    ATV_LSS_MS_I_ItemPrev = etree.SubElement(ATV_LSS_MS_I_Item, 'preview')
    ATV_LSS_MS_I_ItemKP = etree.SubElement(ATV_LSS_MS_I_ItemPrev, 'keyedPreview')
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'title')
    ATV_LSS_MS_I_ItemKP_x.text = "SageTV System Status"
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'summary')
    ATV_LSS_MS_I_ItemKP_x.text = "This is currently a placeholder to show overall system status"
    # The image tag is required, but can be empty
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'image')
    ATV_LSS_MS_I_ItemKP_x.text = "http://" + stv_cnct_ip + "/thumbnails/SageTVLogo.jpg"

    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'metadataKeys')
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "Sage Version"
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "Available Storage"
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "Something?"
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "Something else"

    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'metadataValues')
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "0.2"
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "128 of 2.5"
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "SageConnect"
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "Stuff"


#    # No Longer Used Recorded Show List
#    href = "atv.loadURL('http://" + stv_cnct_ip + "/recordedShows.xml')"
#    label = "Recorded Shows List"


    #
    # Add "Recorded Shows" entry.... Have this display a grid!
    #
    href = "http://" + stv_cnct_ip + "/recordedGrid.xml"
    hdrhref = "atv.loadURL('" + href + "')"
    label = "Recorded Shows"
    ATV_LSS_MS_I_Item = etree.SubElement(ATV_LSS_MS_Items, 'twoLineEnhancedMenuItem')
    ATV_LSS_MS_I_Item.set("id", label )
    ATV_LSS_MS_I_Item.set("onPlay", hdrhref )
    ATV_LSS_MS_I_Item.set("onSelect", hdrhref )
    ATV_LSS_MS_I_ItemLabel = etree.SubElement(ATV_LSS_MS_I_Item, 'label')
    ATV_LSS_MS_I_ItemLabel.text = label
    ATV_LSS_MS_I_ItemImg = etree.SubElement(ATV_LSS_MS_I_Item, 'image')
    ATV_LSS_MS_I_ItemImg.text = "http://" + stv_cnct_ip + "/thumbnails/recorded.png"
    ATV_LSS_MS_I_ItemPrev = etree.SubElement(ATV_LSS_MS_I_Item, 'preview')
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemPrev, 'link')
    ATV_LSS_MS_I_ItemKP_x.text = href + "=Preview"


    #
    # Add "Media Library" entry.... Have this display a grid!
    #
    href = "http://" + stv_cnct_ip + "/mediaPath.xml="
    hdrhref = "atv.loadURL('" + href + "')"
    label = "Media Library"
    ATV_LSS_MS_I_Item = etree.SubElement(ATV_LSS_MS_Items, 'twoLineEnhancedMenuItem')
    ATV_LSS_MS_I_Item.set("id", label )
    ATV_LSS_MS_I_Item.set("onPlay", hdrhref )
    ATV_LSS_MS_I_Item.set("onSelect", hdrhref )
    ATV_LSS_MS_I_ItemLabel = etree.SubElement(ATV_LSS_MS_I_Item, 'label')
    ATV_LSS_MS_I_ItemLabel.text = label
    ATV_LSS_MS_I_ItemImg = etree.SubElement(ATV_LSS_MS_I_Item, 'image')
    ATV_LSS_MS_I_ItemImg.text = "http://" + stv_cnct_ip + "/thumbnails/media.png"
    ATV_LSS_MS_I_ItemPrev = etree.SubElement(ATV_LSS_MS_I_Item, 'preview')
    ATV_LSS_MS_I_ItemKP = etree.SubElement(ATV_LSS_MS_I_ItemPrev, 'keyedPreview')
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'title')
    ATV_LSS_MS_I_ItemKP_x.text = label
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'summary')
    ATV_LSS_MS_I_ItemKP_x.text = "This should be a grid or shelf??"
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'image')
#    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'link')
    ATV_LSS_MS_I_ItemKP_x.text = "http://" + stv_cnct_ip + "/thumbnails/media.png"

    #
    # Add "Media Search" entry.... Have this display a search??!
    #
    href = "http://" + stv_cnct_ip + "/mediaSearch?"
    hdrhref = "atv.loadURL('" + href + "')"
    label = "Media Search"
    ATV_LSS_MS_I_Item = etree.SubElement(ATV_LSS_MS_Items, 'twoLineEnhancedMenuItem')
    ATV_LSS_MS_I_Item.set("id", label )
    ATV_LSS_MS_I_Item.set("onPlay", hdrhref )
    ATV_LSS_MS_I_Item.set("onSelect", hdrhref )
    ATV_LSS_MS_I_ItemLabel = etree.SubElement(ATV_LSS_MS_I_Item, 'label')
    ATV_LSS_MS_I_ItemLabel.text = label
    ATV_LSS_MS_I_ItemImg = etree.SubElement(ATV_LSS_MS_I_Item, 'image')
    ATV_LSS_MS_I_ItemImg.text = "http://" + stv_cnct_ip + "/thumbnails/search.png"
    ATV_LSS_MS_I_ItemPrev = etree.SubElement(ATV_LSS_MS_I_Item, 'preview')
    ATV_LSS_MS_I_ItemKP = etree.SubElement(ATV_LSS_MS_I_ItemPrev, 'keyedPreview')
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'title')
    ATV_LSS_MS_I_ItemKP_x.text = "Imported Media Title Search"
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'summary')
    ATV_LSS_MS_I_ItemKP_x.text = "You can use this to seach across all imported media"
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'image')
    ATV_LSS_MS_I_ItemKP_x.text = "http://" + stv_cnct_ip + "/thumbnails/search.png"

    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'metadataKeys')
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "Version"
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "Authors"
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "Homepage"
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "Forum"

    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'metadataValues')
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "0.2"
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "Me!"
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "SageConnect"
    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
    ATV_LSS_MS_I_ItemKP_xy.text = "Stuff"

#    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemPrev, 'link')
#    ATV_LSS_MS_I_ItemKP_x.text = href


    ATV_LSS_MenuSections = etree.SubElement(ATV_LSS_Sections, 'menuSection')
    ATV_LSS_MS_Items = etree.SubElement(ATV_LSS_MenuSections, 'header')
    ATV_LSS_MS_Itemx = etree.SubElement(ATV_LSS_MS_Items, 'horizontalDivider')
    ATV_LSS_MS_Itemx.set('alignment','left')
    ATV_LSS_MS_Itemx = etree.SubElement(ATV_LSS_MS_Itemx, 'title')

#        <horizontalDivider alignment="left">
#            <title>{{TEXT(Video)}}</title>
#        </horizontalDivider>


#<header>
#    <textDivider alignment="left">
#        <title>Options</title>
#    </textDivider>


    ATV_LSS_MS_Items = etree.SubElement(ATV_LSS_MenuSections, 'items')

#
#    href = "atv.loadURL('http://trailers.apple.com/appletv/index.xml')"
#    label = "Trailers"
#    ATV_LSS_MS_MenuItem = etree.SubElement(ATV_LSS_MS_Items, 'oneLineMenuItem')
#    ATV_LSS_MS_MenuItem.set("id", "list_7" )
#    ATV_LSS_MS_MenuItem.set("onSelect", href )
#    ATV_LSS_MS_MenuItemLabel = etree.SubElement(ATV_LSS_MS_MenuItem, 'label')
#    ATV_LSS_MS_MenuItemLabel.text = label
#    ATV_LSS_MS_MenuItemAcc = etree.SubElement(ATV_LSS_MS_MenuItem, 'accessories')
#    etree.SubElement(ATV_LSS_MS_MenuItemAcc, 'arrow')


#    hdrhref = "atv.loadURL('http://trailers.apple.com/appletv/index.xml')"
    hdrhref = "atv.loadURL('http://trailers.apple.com/appletv/us/nav.xml')"
    label = "Trailers"
    ATV_LSS_MS_I_Item = etree.SubElement(ATV_LSS_MS_Items, 'twoLineEnhancedMenuItem')
    ATV_LSS_MS_I_Item.set("id", label )
    ATV_LSS_MS_I_Item.set("onPlay", hdrhref )
    ATV_LSS_MS_I_Item.set("onSelect", hdrhref )
    ATV_LSS_MS_I_ItemLabel = etree.SubElement(ATV_LSS_MS_I_Item, 'label')
    ATV_LSS_MS_I_ItemLabel.text = label
    ATV_LSS_MS_I_ItemImg = etree.SubElement(ATV_LSS_MS_I_Item, 'image')
    ATV_LSS_MS_I_ItemImg.text = "http://" + stv_cnct_ip + "/thumbnails/Trailers.png"
    ATV_LSS_MS_I_ItemPrev = etree.SubElement(ATV_LSS_MS_I_Item, 'preview')
    ATV_LSS_MS_I_ItemKP = etree.SubElement(ATV_LSS_MS_I_ItemPrev, 'keyedPreview')
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'title')
    ATV_LSS_MS_I_ItemKP_x.text = "(initial) Apple Trailers Support"
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'summary')
    ATV_LSS_MS_I_ItemKP_x.text = "Look through AppleTV Trailers to find whats new"
    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'image')
    ATV_LSS_MS_I_ItemKP_x.text = "http://" + stv_cnct_ip + "/thumbnails/Trailers.png"




    href = "atv.loadURL('http://" + stv_cnct_ip + "/exampleLayouts=')"
    label = "Layout Examples"
    ATV_LSS_MS_MenuItem = etree.SubElement(ATV_LSS_MS_Items, 'oneLineMenuItem')
    ATV_LSS_MS_MenuItem.set("id", "list_5" )
    ATV_LSS_MS_MenuItem.set("onSelect", href )
    ATV_LSS_MS_MenuItemLabel = etree.SubElement(ATV_LSS_MS_MenuItem, 'label')
    ATV_LSS_MS_MenuItemLabel.text = label
    ATV_LSS_MS_MenuItemAcc = etree.SubElement(ATV_LSS_MS_MenuItem, 'accessories')
    etree.SubElement(ATV_LSS_MS_MenuItemAcc, 'arrow')


#    print XML_prettystring(ATVRoot)
    return ATVRoot

'''
Connect to the SageTV server
Download the list of recorded shows
Parse and turn it into an appropriate list
'''
def makeRecordedShowList():
    dprint(__name__, 1, "====== makeRecordedShowList ======" )
    InitCfg()
    
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
    ATVListWPreview = etree.SubElement(ATVBody, 'optionDialog')
    ATVListWPreview.set('id', "Show_List")
#    ATVListWPreview.set('volatile', "true")
#    ATVListWPreview.set('onVolatileReload', "atv.loadAndSwapURL(http://" + stv_cnct_ip + "/recordedShows.xml)")

    ATV_LSS_Header = etree.SubElement(ATVListWPreview, 'header')
    ATV_LSS_SimpleHeader = etree.SubElement(ATV_LSS_Header, 'simpleHeader')
    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'title')
    ATV_LSS_SH_Title.text = "Recordings"
    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'subtitle')
    ATV_LSS_SH_Title.text = "Currently Available Shows"
    

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
    stv_address = username + ":" + password + "@" + sagetv_ip
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
                    href = href.replace(' ', '+')
                    href = href.replace('\'', '&apos;')

                    # make sure there are no spaces in the href
                    href = "atv.loadURL('http://" + stv_cnct_ip + "/title=" + href + "')"
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
                    ATV_LSS_MS_MI_P_CFP_I.text = stv_address + "/sagex/media/poster/" + href[href.rfind('='):]

    return ATVRoot

#
# Create a grid layout of recorded titles
#
def makeTitleGrid(path):
    dprint(__name__, 1, "====== makeTitleGrid ======" )
    InitCfg()

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
    if path.find('Preview') > 0:
        ATVprv = etree.SubElement(ATVBody, 'preview')
        ATVScroller = etree.SubElement(ATVprv, 'scrollerPreview')
    else:
        ATVScroller = etree.SubElement(ATVBody, 'scroller')

    ATVScroller.set('id', "com.sample.show-grid")
#    ATVScroller.set('volatile', "true")
#    ATVScroller.set('onVolatileReload', "atv.loadAndSwapURL(http://" + stv_cnct_ip + "/SageConnect.xml)")

    ATV_S_Header = etree.SubElement(ATVScroller, 'header')

    if path.find('Preview') > 0:
        ATV_S_SimpleHeader = etree.SubElement(ATV_S_Header, 'metadataHeader')
    else:
        ATV_S_SimpleHeader = etree.SubElement(ATV_S_Header, 'simpleHeader')

    ATV_S_SH_Title = etree.SubElement(ATV_S_SimpleHeader, 'title')
    ATV_S_SH_Title.text = "SageTV Recordings"
    ATV_S_SH_Title = etree.SubElement(ATV_S_SimpleHeader, 'subtitle')
    ATV_S_SH_Title.text = "All Available Shows"
    


    #<items>
    #    <grid columnCount="7" id="grid_0">
    #        <items>
    ATV_S_Items = etree.SubElement(ATVScroller, 'items')
    ATV_S_I_Grid = etree.SubElement(ATV_S_Items, 'grid')

    if path.find('Preview') > 0:
        ATV_S_I_Grid.set("columnCount","5")
    else:
        ATV_S_I_Grid.set("columnCount","7")


    ATV_S_I_Grid.set("id","grid_0")
    ATV_S_I_G_Items = etree.SubElement(ATV_S_I_Grid, 'items')

    count = 0
    ShowList = etree.Element("root")

    #
    # Get the XML from the SageTV Server
    #
    stv_address = username + ":" + password + "@" + sagetv_ip
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
                    
                    inputNode = title.find('input')
                    if inputNode is not None:
                        MediaId = inputNode.get('value')
                        if MediaId.find(',') > 0:
                            MediaId = MediaId[:MediaId.find(',')]

                    count = count + 1
                    dprint(__name__, 2, "----------> <{0} class={1}>", title.tag, title.get('class') )
                    thisshow = title.find('a')
                    dprint(__name__, 2, "-----------* {0}", thisshow.text )
                    showname = thisshow.text

                    href = thisshow.get("href")
                    href = href[href.index("title="):]
                    href = href[href.index("=") + 1:]
                    href = href.replace(' ', '+')
                    href = href.replace('\'', '&apos;')

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
                    hdrTemp = "atv.sessionStorage['addrpms']='" + stv_cnct_ip + "';" + href
                    ATV_S_I_G_I_mP.set("onPlay",href)
                    ATV_S_I_G_I_mP.set("onSelect",href)
#                    ATV_S_I_G_I_mP.set("onHoldSelect","scrobbleMenu('name', 'rating', 'http://" + stv_cnct_ip + ");" )


                    ATV_S_I_G_I_mP_T = etree.SubElement(ATV_S_I_G_I_mP, 'title')
                    ATV_S_I_G_I_mP_T.text = showname
#                    ATV_S_I_G_I_mP_T = etree.SubElement(ATV_S_I_G_I_mP, 'subtitle')
#                    ATV_S_I_G_I_mP_T.text = title
                    ATV_S_I_G_I_mP_T = etree.SubElement(ATV_S_I_G_I_mP, 'image')
                    ATV_S_I_G_I_mP_T.text = stv_address + "/sagex/media/fanart?mediafile=" + MediaId + "&artifact=poster"
#                    print "--> " + ATV_S_I_G_I_mP_T.text
                    ATV_S_I_G_I_mP_T = etree.SubElement(ATV_S_I_G_I_mP, 'defaultImage')
                    ATV_S_I_G_I_mP_T.text = "resource://Poster.png"
#                    ATV_S_I_G_I_mP_T.text = "resource://16X9.png"

#    print XML_prettystring(ATVRoot)

    return ATVRoot

#
# Query the SageTv server and get a list of all eppisodes
# for the selected show
#
def makeShowList(atvTitle):
    dprint(__name__, 1, "====== makeShowList ======: {0}", atvTitle )
    InitCfg()
        
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


    #<atv>
    #    <head>
    #        <script src="{{URL(:/js/utils.js)}}" />
    #    </head>
    ATVRoot = etree.Element("atv")
    ATVHead = etree.SubElement(ATVRoot, 'head')
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"http://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/utils.js")


    #	<body>
    #		<listScrollerSplit id="com.sample.list-scroller-split">
    ATVBody = etree.SubElement(ATVRoot, 'body')

    #    ATVLSS = etree.SubElement(ATVBody, 'optionDialog') # Centered and Centered!
    #    ATVLSS.set('id', "com.sample.movie-grid")


    ATVLSS = etree.SubElement(ATVBody, 'listScrollerSplit') # Centered and Centered!
    ATVLSS.set('id', "com.menu.Main.list-scroller-split")
    ##    ATVListWPreview.set('volatile', "true")
    ##    ATVListWPreview.set('onVolatileReload', "atv.loadAndSwapURL('http://" + stv_cnct_ip  + "/SageConnect.xml')")

    #<header>
    #    <simpleHeader>
    #        <title>Movie Trailers</title>
    #        <subtitle>SubTitle</subtitle>
    #    </simpleHeader>
    #</header>
    ATV_LSS_M_H = etree.SubElement(ATVLSS, 'header')
    ATV_LSS_M_H_sH = etree.SubElement(ATV_LSS_M_H, 'simpleHeader')
    ATV_LSS_M_H_sH_t = etree.SubElement(ATV_LSS_M_H_sH, 'title')
    titleText = atvTitle[atvTitle.find('=')+1:]
    titleText = titleText.replace('+',' ')
    titleText = unquote_plus(titleText)
    ATV_LSS_M_H_sH_t.text = titleText
#    ATV_LSS_M_H_sH_t = etree.SubElement(ATV_LSS_M_H_sH, 'subtitle')
#    ATV_LSS_M_H_sH_t.text = "Current Episodes"


    #        <menu>
    #            <sections>
    #                <menuSection>
    #                   <items>
    ATV_LSS_Menu = etree.SubElement(ATVLSS, 'menu')
    ATV_LSS_Sections = etree.SubElement(ATV_LSS_Menu, 'sections')
    ATV_LSS_MenuSections = etree.SubElement(ATV_LSS_Sections, 'menuSection')


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
                        
#                        ## delete this
#                        href = "{var ev = ''; var out = [];for (ev in window){if (/^on/.test(ev)) {out[out.length] = ev;}}log(out.join(', '));};" + href

                        
                        dprint(__name__, 2, "---- href ---> {0}", href )

                        # Get the show name
                        mediaId = title.find('input')
                        if mediaId is not None:
                            mediaId = mediaId.get('value')
                        else:
                            mediaId = ""


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

                        if eps.text is not None:
                            if eps.text.find(".") > 0:
                                if eps.text.find("GB") < 0:
                                    if eps.text.find("MB") < 0:
                                        # this is the episode description
                                        episodeDesc = eps.text

                        if eps.text is not None and eps.text.find(":") > 0:
                            # this is the original airing time
                            episodeDate = eps.text
                            # grab just the airing date (remove day and time)
#                            episodeDate = episodeDate[episodeDate.find(',') + 1:]
#                            episodeDate = episodeDate[:episodeDate.rfind(',')]
#                            episodeDate = episodeDate.strip()

                        if eps.find('img') is not None:
                            # these are the images that tell view status
                            img = ""


                    # make sure that something is in the title even if its just the show name
                    if episodeTitle == "":
                        episodeTitle = showTitle





                    # Repeat for each item in the list
                    #<items>
                    #    <twoLineEnhancedMenuItem id="1a"
                    #        onPlay="atv.loadURL('http://SageConnect.Server/exampleLayouts=scroller.xml')"
                    #        onSelect="atv.loadURL('http://SageConnect.Server/exampleLayouts=scroller.xml')">
                    #        <label>TV</label>
                    #        <label2>Recorded Television</label2>
                    #        <image>http://SageConnect.Server/thumbnails/TvIcon.png</image>
                    #        <!--<defaultImage>resource://Poster.png</defaultImage>-->
                    #        <preview>
                    #            <keyedPreview>
                    #                <title>Recorded Television</title>
                    #                <summary>27 Shows (285 Recordings)</summary>
                    #                <image>http://SageConnect.Server/thumbnails/SageTVLogo.jpg</image>
                    #            </keyedPreview>
                    #        </preview>
                    #    </twoLineEnhancedMenuItem>
                    #</items>


                    #
                    # Add Generic SageTV item.... use this to show current status
                    #
                    href = "http://" + stv_cnct_ip + "/MediaId.xml="
                    hdrhref = "atv.loadURL('" + href + mediaId + "')"
                    ATV_LSS_MS_I_Item = etree.SubElement(ATV_LSS_MS_Items, 'oneLineMenuItem')
                    ATV_LSS_MS_I_Item.set("id", episodeTitle )
                    ATV_LSS_MS_I_Item.set("onPlay", hdrhref )
                    ATV_LSS_MS_I_Item.set("onSelect", hdrhref )
                    ATV_LSS_MS_I_ItemLabel = etree.SubElement(ATV_LSS_MS_I_Item, 'label')
                    ATV_LSS_MS_I_ItemLabel.text = episodeTitle
#                    ATV_LSS_MS_I_ItemImg = etree.SubElement(ATV_LSS_MS_I_Item, 'image')
##                    ATV_LSS_MS_I_ItemImg.text = "http://" + stv_cnct_ip + "/thumbnails/Ball.png"
#                    ATV_LSS_MS_I_ItemImg = etree.SubElement(ATV_LSS_MS_I_Item, 'defaultImage')
                    ATV_LSS_MS_I_ItemPrev = etree.SubElement(ATV_LSS_MS_I_Item, 'preview')
                    ATV_LSS_MS_I_ItemKP = etree.SubElement(ATV_LSS_MS_I_ItemPrev, 'keyedPreview')
                    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'title')
                    ATV_LSS_MS_I_ItemKP_x.text = episodeTitle
                    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'summary')
                    if episodeDesc <> "":
                        ATV_LSS_MS_I_ItemKP_x.text = episodeDesc

                    # The image tag is required, but can be empty
                    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'image')
                    ATV_LSS_MS_I_ItemKP_x.text = "http://" + sagetv_ip + "/stream/MediaFileThumbnailServlet?MediaFileId=" + mediaId
                    
                    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'metadataKeys')
                    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
                    ATV_LSS_MS_I_ItemKP_xy.text = "Recorded"
                    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
                    ATV_LSS_MS_I_ItemKP_xy.text = "Duration"

                    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'metadataValues')
                    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
                    ATV_LSS_MS_I_ItemKP_xy.text = episodeDate
                    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
                    ATV_LSS_MS_I_ItemKP_xy.text = "20 M"

                        
    return ATVRoot


def makeMediaInfo(atvAiring):
    dprint(__name__, 1, "====== makeMediaInfo ======: {0}", atvAiring )
    InitCfg()
        
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
    epCategory = ""


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

                                # find episode Category:
                                if div4.find('b') <> None and div4.find('b').text == "Category:":
                                    epCategory = div4[0].tail
                                    epCategory = epCategory.strip(' \t\n\r')
                                    if epCategory.find('ReRun') > 0:
                                        epCategory = epCategory[:epCategory.rfind('-')]
                                        epCategory = epCategory.strip()
                                    dprint(__name__, 2, "epCategory --> {0}", epCategory )


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

#    posterTmp = "http://" + username + ":" + password + "@" + sagetv_ip + textURL
    posterTmp = "http://" + username + ":" + password + "@" + sagetv_ip
#    ATV_ID_BigPoster.text = posterTmp + "/stream/MediaFileThumbnailServlet?MediaFileId=" + epMediaID
    ATV_ID_BigPoster.text = posterTmp + "/sagex/media/poster/" + epMediaID
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

#    ColumnDefinitionText = ['Details', 'Actors', 'Directors', 'Producers']
#    for cdCount in range (0,4):
#        ATV_ID_T_CD1 = etree.SubElement(ATV_ID_T_CD, 'columnDefinition')
#        ATV_ID_T_CD1.set("width","25")
#        ATV_ID_T_CD1.set("alignment","left")
#        ATV_ID_T_CD1_title = etree.SubElement(ATV_ID_T_CD1, 'title')
#        ATV_ID_T_CD1_title.text = ColumnDefinitionText[cdCount]

    ColumnDefinitionText = ['Details', 'Starring']
    for cdCount in range (0,2):
        ATV_ID_T_CD1 = etree.SubElement(ATV_ID_T_CD, 'columnDefinition')
        ATV_ID_T_CD1.set("width","50")
        ATV_ID_T_CD1.set("alignment","center")
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
    
    rowText = [epCategory, 'Role tag']
    ATV_ID_T_Row = etree.SubElement(ATV_ID_T_Rows, 'row')
    for cdCount in range (0,2):
        ATV_ID_T_Row_Label = etree.SubElement(ATV_ID_T_Row, 'label')
        ATV_ID_T_Row_Label.text = rowText[cdCount]

    #        <row>
    #            <label>{{getDurationString(Video/duration)}}</label>
    #            <label>{{VAL(Video/Role[2]/tag)}}</label>
    #            <label>{{VAL(Video/Director[2]/tag)}}</label>
    #            <label>{{VAL(Video/Producer[2]/tag)}}</label>
    #        </row>
    rowText = [epDuration, 'Role tag2']
    ATV_ID_T_Row = etree.SubElement(ATV_ID_T_Rows, 'row')
    for cdCount in range (0,2):
        ATV_ID_T_Row_Label = etree.SubElement(ATV_ID_T_Row, 'label')
        ATV_ID_T_Row_Label.text = rowText[cdCount]

    #        <row>
    #            <label>{{VAL(Video/Media/videoResolution:Unknown:1080=1080p|720=720p|576=SD|480=SD|sd=SD)}}   {{VAL(Video/Media/audioCodec:Unknown:ac3=AC3|aac=AAC|mp3=MP3|dca=DTS|drms=DRMS)}} {{VAL(Video/Media/audioChannels:Unknown:2=Stereo|6=5.1|8=7.1)}} </label>
    #            <label>{{VAL(Video/Role[3]/tag)}}</label>
    #            <label>{{VAL(Video/Director[3]/tag)}}</label>
    #            <label>{{VAL(Video/Producer[3]/tag)}}</label>
    #        </row>
    rowText = ['1080p AC3 5.1', 'Role tag3']
    ATV_ID_T_Row = etree.SubElement(ATV_ID_T_Rows, 'row')
    for cdCount in range (0,2):
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
    rowText = ['', 'Role tag4']
    ATV_ID_T_Row = etree.SubElement(ATV_ID_T_Rows, 'row')
    ATV_ID_T_Row_Star = etree.SubElement(ATV_ID_T_Row, 'starRating')
    ATV_ID_T_Row_Star.set("hasUserSetRating", "true")
    ATV_ID_T_Row_S_Pct = etree.SubElement(ATV_ID_T_Row_Star, 'percentage')
    ATV_ID_T_Row_S_Pct.text = "50"

    for cdCount in range (1,2):
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

    TempStr = "atv.sessionStorage['addrpms']='" + stv_cnct_ip + "';atv.sessionStorage['sageDbId']=" + epMediaID + ";atv.loadURL('http://" + stv_cnct_ip + "/MediaFileId=" + epMediaID + "')"

    ATV_ID_CS_S_S_SS_I_AB.set("onSelect",TempStr)
    ATV_ID_CS_S_S_SS_I_AB.set("onPlay",TempStr)
    ATV_ID_CS_S_S_SS_I_AB_Title = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'title')
    ATV_ID_CS_S_S_SS_I_AB_Title.text = "Play"
    ATV_ID_CS_S_S_SS_I_AB_Img = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'image')
    ATV_ID_CS_S_S_SS_I_AB_Img.text = "resource://Play.png"
    ATV_ID_CS_S_S_SS_I_AB_Img = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'focusedImage')
    ATV_ID_CS_S_S_SS_I_AB_Img.text = "resource://PlayFocused.png"

# http://sagetv.ursaminor.net:80/sage/public/MediaFile?MediaFileId=11174811&Segment=0


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
#    ATV_ID_CS_S_S_SS_I_AB = etree.SubElement(ATV_ID_CS_S_S_SS_I, 'actionButton')
#    ATV_ID_CS_S_S_SS_I_AB.set("id","selectAudioAndSubs")
#    TempStr = "atv.sessionStorage['addrpms']='" + stv_cnct_ip + "';atv.loadURL('http://" + stv_cnct_ip + "/MediaFileId=" + epMediaID + "')"
#    ATV_ID_CS_S_S_SS_I_AB.set("onSelect",TempStr)
#    ATV_ID_CS_S_S_SS_I_AB.set("onPlay",TempStr)
#    ATV_ID_CS_S_S_SS_I_AB_Title = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'title')
#    ATV_ID_CS_S_S_SS_I_AB_Title.text = "More"
#    ATV_ID_CS_S_S_SS_I_AB_Img = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'image')
#    ATV_ID_CS_S_S_SS_I_AB_Img.text = "resource://More.png"
#    ATV_ID_CS_S_S_SS_I_AB_Img = etree.SubElement(ATV_ID_CS_S_S_SS_I_AB, 'focusedImage')
#    ATV_ID_CS_S_S_SS_I_AB_Img.text = "resource://MoreFocused.png"



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
    dprint(__name__, 1, "====== makePlay ======: {0}", atvAiring )
    InitCfg()
    
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

    time = "0"
    # verify the bookmark dir exists
    if os.path.exists("bookmarks"):
        sageDbId = textURL[textURL.rfind("=")+1:]

        # if the bookmark file
        if os.path.isfile("bookmarks/" + sageDbId + ".bk"):

            # if the file exists, read it
            file = codecs.open("bookmarks/" + sageDbId + ".bk", "r", "utf-8")
            time = file.read()
            file.close()

    print "time => [" + time + "]"

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

    # Dont bother to resume if less than 1 second into video
#    if int(time) > 1000:
    # resume from some position within the file stream
    # the number is seconds000  so 20 seconds would be "20000"
#    ATV_VP_hFVA_mU = etree.SubElement(ATV_VP_hFVA, 'bookmarkTime')
#    ATV_VP_hFVA_mU.text = "20000"

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

    ATV_VP_hFVA_mMd = etree.SubElement(ATV_VP_hFVA, 'myMetadata')
    ATV_VP_hFVA_mMd_hfva = etree.SubElement(ATV_VP_hFVA_mMd, 'httpFileVideoAsset')
    ATV_VP_hFVA_mMd_hfva.set('id','com.sample.video-player1')
    ATV_VP_hFVA_mMd_hfva_tmp = etree.SubElement(ATV_VP_hFVA_mMd_hfva, 'mediaURL')
    ATV_VP_hFVA_mMd_hfva_tmp.text = textURL
    ATV_VP_hFVA_mMd_hfva_tmp = etree.SubElement(ATV_VP_hFVA_mMd_hfva, 'title')
    ATV_VP_hFVA_mMd_hfva_tmp.text = "title"
    ATV_VP_hFVA_mMd_hfva_tmp = etree.SubElement(ATV_VP_hFVA_mMd_hfva, 'description')
    ATV_VP_hFVA_mMd_hfva_tmp.text = "description"

    return ATVRoot



def makeDirTree():
    # Specifically build imported media tree
    # this will look to see if we have saved a dir tree, if not, it will generate the xml and save it.
    # how often do I need to regenerate?  once a month ish?
    dprint(__name__, 1, "====== makeDirTree ======" )
    InitCfg()
        
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
                    
                    # possible fix for linux paths
                    # replace all forward slashes with back slashes
                    # remove the first slash, so that it is like the " drive" letter
                    path = path.replace('/','\\')
                    path = path.strip('\\')
                    
                    # parse the file path
                    # make me a sub function probably
                    if path is not "":
                        # also part of working on a Linux path
                        diskLetter = path[:path.find(":") + 1]
                        if diskLetter == "":
                            diskLetter = path[:path.find("\\")]
                        
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
    dprint(__name__, 1, "====== findNode ======: xmlRoot : {0}", Path)

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
    
    dprint(__name__, 0, "Could not find path: {0}", Path )
    
    return None


#
# Generate the XML to display the dir list on screen
# Have it call back with the full path
#
def generatePathXML(path, myList):
    dprint(__name__, 1, "====== generatePathXML ======: myList : {0}", path)
    InitCfg()
        
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
    
    #	<body>
    #		<scroller id="com.sample.scroller">
    #			<header>
    #				<simpleHeader>
    #					<title>Shows by Name</title>
    #					<subtitle>List all shows by their names</subtitle>
    #				</simpleHeader>
    #			</header>
    ATVBody = etree.SubElement(ATVRoot, 'body')
    ATVScroller = etree.SubElement(ATVBody, 'scroller')
    ATVScroller.set('id', "com.menu.Main.scroller")
    #    ATVListScrollSplit.set('volatile', "true")
    #    ATVListScrollSplit.set('onVolatileReload', atv.loadAndSwapURL('http://" + stv_cnct_ip  + "/" + path + ")")
    
    ATV_LSS_Header = etree.SubElement(ATVScroller, 'header')
    ATV_LSS_SimpleHeader = etree.SubElement(ATV_LSS_Header, 'simpleHeader')
    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'title')
    if path == "":
        titleText = "Imported Media Drives"
    elif path.find('/') <= 0:
        titleText = "Drive " + path[:path.find(':')]
    else:
        titleText = path[path.rfind('/')+1:]
    ATV_LSS_SH_Title.text = titleText
    ATV_LSS_SH_Title = etree.SubElement(ATV_LSS_SimpleHeader, 'subtitle')
    ATV_LSS_SH_Title.text = path
    
    #<items>
    #    <grid columnCount="7" id="grid_1">
    #        <items>
    ATV_LSS_Items = etree.SubElement(ATVScroller, 'items')
    ATV_LSS_I_grid = etree.SubElement(ATV_LSS_Items, 'grid')
    ATV_LSS_I_grid.set('columnCount','7')
    ATV_LSS_I_grid.set('id','grid_1')
    ATV_LSS_Igi = etree.SubElement(ATV_LSS_I_grid, 'items')

    count = 0

    # Make basic list so we can sort it next.
    myStringList = []
    for myItem in myList:
        if myItem.get('sageDbId') is not None:
            myStringList.append( myItem.get('id') + ":" + myItem.get('sageDbId') )
        else:
            myStringList.append( myItem.get('id') + ":" )

    # Get sorted list
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
        href = href + myItem[:myItem.rfind(":")]
        href = href.replace(' ', '+')
        href = href.replace('\'', '&apos;')

        href = "atv.loadURL('http://" + stv_cnct_ip + "/mediaPath.xml=" + href + "')"
        dprint(__name__, 2, "href --> {0}", href)

        ATV_LSS_Igi_MP = etree.SubElement(ATV_LSS_Igi, 'moviePoster')
        ATV_LSS_Igi_MP.set('id', str(count) )
        ATV_LSS_Igi_MP.set('alwaysShowTitles', 'true' )
        ATV_LSS_Igi_MP.set('onPlay', href )
        ATV_LSS_Igi_MP.set('onSelect', href )
        ATV_LSS_IgiMP_A = etree.SubElement(ATV_LSS_Igi_MP, 'title')
        ATV_LSS_IgiMP_A.text = myItem[:myItem.rfind(".")]

        ATV_LSS_IgiMP_B = etree.SubElement(ATV_LSS_Igi_MP, 'image')
        posterTmp = "http://" + username + ":" + password + "@" + sagetv_ip
        ATV_LSS_IgiMP_B.text = posterTmp + "/sagex/media/poster/" + myItem[myItem.rfind(":")+1:]

        fExt = ''
        fName, fExt = os.path.splitext(myItem)
        if fExt == '':
            ATV_LSS_IgiMP_B.text = "http://" + stv_cnct_ip + "/thumbnails/Folder.png"
            print ATV_LSS_IgiMP_B.text


        ATV_LSS_IgiMP_T = etree.SubElement(ATV_LSS_Igi_MP, 'defaultImage')
        ATV_LSS_IgiMP_T.text = 'resource://Poster.png'

#    print XML_prettystring(ATVRoot)
    return ATVRoot




def makeDirList(path):
    dprint(__name__, 1, "====== makeDirList ======: {0}", path)
    InitCfg()
    
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

    # info for file age
    now = time.time()
    twodays_ago = now - 60*60*24*2 # Number of seconds in two days
    if os.path.isfile(filename):
        fileCreation = os.path.getctime(filename)

    # if the directory listing file does not exist
    # or if file is more than two days old, rebuild it
    if not os.path.isfile(filename) or fileCreation < twodays_ago:
        # on demand?  Maybe have a menu item?
        # create it
        XML = makeDirTree()

        file = codecs.open(filename, "w", "utf-8")
        file.write(XML_prettystring(XML))
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
        
        dprint(__name__, 2, "--id -------> {0}", myNode.get('id'))
        if myNode.get('sageDbId') is not None:
            dprint(__name__, 2, "--sageDbId -> {0}", myNode.get('sageDbId'))
            txtTmp = "/MediaId=" + myNode.get('sageDbId')

            return makeMediaInfo(txtTmp)
        else:
            dprint(__name__, 0, "MakeDirList(): There is no MediaFileId for this path: {0}", path )
            return XML_Error("makeDirList", "Unable to make MediaInfo Screen. There is no MediaFileId entry")


    else:
        return generatePathXML(path, myList)

    dprint(__name__, 0, "MakeDirList(): Failed to process path: {0}", path )
    return XML_Error("makeDirList", "Failed to process")


#
# Search all imported media & show titles for specific text?
#
#
#
def searchTitle():
    dprint(__name__, 1, "====== searchTitle ======")
    InitCfg()
    
    # Get the IP of the SageTV Connect Server
    # -- hopefully this is the same server soon
    if g_param['CSettings'].getSetting('ip_webserver')<>'':
        stv_cnct_ip = g_param['CSettings'].getSetting('ip_webserver')
    
#    <atv>
#        <body>
#            <search id="plex-search">
#                <header>
#                    <simpleHeader>
#                        <title>{{TEXT(Search Plex Library)}}</title>
#                    </simpleHeader>
#                </header>
#                <baseURL>{{URL(:/search?type=4&amp;query=)}}</baseURL>
#           </search>
#       </body>
#    </atv>
    ATVRoot = etree.Element("atv")
    ATVBody = etree.SubElement(ATVRoot, 'body')
    ATVBody_S = etree.SubElement(ATVBody, 'search')
    ATVBody_S.set('id',"sage-search")
    ATVBody_S_h = etree.SubElement(ATVBody_S, 'header')
    ATVBody_S_h_sH = etree.SubElement(ATVBody_S_h, 'simpleHeader')
    ATVBody_S_h_sH_t = etree.SubElement(ATVBody_S_h_sH, 'title')
    ATVBody_S_h_sH_t.text = "SageTV Title Search"
    ATVBody_S_bU = etree.SubElement(ATVBody_S, 'baseURL')
#    ATVBody_S_bU.text = "http://" + stv_cnct_ip + "/search?type=4&amp;query="
    ATVBody_S_bU.text = "http://" + stv_cnct_ip + "/search?query="
    return ATVRoot


def searchMedia(path):
    dprint(__name__, 1, "====== searchMedia ======: {0}", path)
    InitCfg()
    
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

    #<atv>
    #    <head>
    #        <script src="{{URL(:/js/utils.js)}}" />
    #        <script src="{{URL(:/js/scrobble.js)}}" />
    #    </head>

    ATVRoot = etree.Element("atv")
    ATVHead = etree.SubElement(ATVRoot, 'head')
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"https://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/utils.js")
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"https://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/scrobble.js")


#        <body>
#            <searchResults id="searchResults">
#                <menu>
#                    <sections>
    ATVBody = etree.SubElement(ATVRoot, 'body')
    ATVBody_sR = etree.SubElement(ATVBody, 'searchResults')
    ATVBody_sR.set('id', 'searchResults')
    ATVBody_sR_m = etree.SubElement(ATVBody_sR, 'menu')
    ATVBody_sR_m_s = etree.SubElement(ATVBody_sR_m, 'sections')

# can repeat with mutiple menuSections
#    <menuSection>
#        <header>
#            <horizontalDivider alignment="left">
#                <title>{{TEXT(Movies)}}</title>
#            </horizontalDivider>
#        </header>
#        <items>{{VAR(cut:NoKey:CUT)}}  <!--this sets the var to CUT-->
    ATVBody_sR_m_s_mS = etree.SubElement(ATVBody_sR_m_s, 'menuSection')
    ATVBody_sR_m_s_mS_h = etree.SubElement(ATVBody_sR_m_s_mS, 'header')
    ATVBody_sR_m_s_mS_h_hD = etree.SubElement(ATVBody_sR_m_s_mS_h, 'horizontalDivider')
    ATVBody_sR_m_s_mS_h_hD.set('alignment', 'left')
    ATVBody_sR_m_s_mS_h_hD_t = etree.SubElement(ATVBody_sR_m_s_mS_h_hD, 'title')
    ATVBody_sR_m_s_mS_h_hD_t.text = "This is the section title"
    ATVBody_sR_m_s_mS_i = etree.SubElement(ATVBody_sR_m_s_mS, 'items')

    filename = 'dirList.xml'
    file = open(filename, "r")

# Only disply first 10 finds
# For each line, grep to see if it has the text in it.....
#   If count > 10, stop
#
#   If line contains text, put it in the file
#   increment count
#
#

    searchTmp = path[path.find('=')+1:]
    print "st--> " + searchTmp
    searchTmp = unquote_plus(searchTmp)
    print "st--> " + searchTmp
    searchTmp = searchTmp.lower()
    print "st--> " + searchTmp

    id = int(0)


# if < max results
# strip out the title
# look for match
# if yes, strip out ID
# generate entry
    for line in file:
        # if more than 15 entries stop.
        if id > 15:
            break
        
        lineTmp = line[line.find("\"")+1:]
        lineTmp = lineTmp[:lineTmp.find("\"")]
        lineTmp2 = lineTmp.lower()
        print "lt--> " + lineTmp

        if lineTmp2.find(searchTmp) >= 0:
            if lineTmp2.find("<") >= 0:
                dbidTmp = ""
                print "no quotes, ignore "
                continue
            elif lineTmp2.find(".") <= 0:
                # I'm a dir... make my link to the build dir? thing
                dbidTmp = ""
                print "found dir, ignore "
                continue
            else:
                # pull out the ID
                # create an entry
                dbidTmp = line[line.rfind("sageDbId=") + 10 :]
                dbidTmp = dbidTmp[:dbidTmp.find("\"")]
                print "dt--> " + dbidTmp




# Can repeat multiple items within a menuSection
# specifically, multiple twoLineEnhancedMenuItems within the items section
#
#        <twoLineEnhancedMenuItem id="{{VAL(key)}}"
#            onPlay="atv.sessionStorage['addrpms']='{{ADDR_PMS()}}';{{sendToATV(ratingKey:0:duration:0)}};atv.loadURL('{{URL(key)}}&amp;PlexConnect=Play')"
#            onSelect="atv.sessionStorage['addrpms']='{{ADDR_PMS()}}';{{sendToATV(ratingKey:0:duration:0)}};atv.loadURL('{{URL(key)}}&amp;PlexConnect=MoviePrePlay')"
#            onHoldSelect="scrobbleMenu('{{TEXT(Movie)}}', '{{VAL(ratingKey)}}', '{{ADDR_PMS()}}');">
#                {{COPY(Video:type::movie=COPY|episode=)}}
#                {{VAR(cut:NoKey:)}}  <!--this sets the var to None-->
#                <label>{{VAL(title)}}</label>
#                <image>{{IMAGEURL(thumb)}}</image>
#                <defaultImage>resource://Poster.png</defaultImage>
#            </twoLineEnhancedMenuItem>
            ATVBody_sR_m_s_mS_i_tLEMI = etree.SubElement(ATVBody_sR_m_s_mS_i, 'twoLineEnhancedMenuItem')
            ATVBody_sR_m_s_mS_i_tLEMI.set('id','tLEMI_'+str(id) )
            id = id + 1

            txtTmp = "atv.sessionStorage['addrpms']='" + stv_cnct_ip + "';atv.loadURL('http://" + stv_cnct_ip
            ATVBody_sR_m_s_mS_i_tLEMI.set('onPlay', txtTmp + "/MediaFileId=" + dbidTmp  + "')")
            ATVBody_sR_m_s_mS_i_tLEMI.set('onSelect', txtTmp + "/MediaId=" + dbidTmp + "')" )
            ATVBody_sR_m_s_mS_i_tLEMI.set('onHoldSelect', txtTmp + "/MediaId=" + dbidTmp  + "')" )

            ATVBody_sR_m_s_mS_i_tLEMI_l = etree.SubElement(ATVBody_sR_m_s_mS_i_tLEMI, 'label')
            ATVBody_sR_m_s_mS_i_tLEMI_l.text = lineTmp
            ATVBody_sR_m_s_mS_i_tLEMI_i = etree.SubElement(ATVBody_sR_m_s_mS_i_tLEMI, 'image')
            ATVBody_sR_m_s_mS_i_tLEMI_i.text = "http://" + sagetv_ip + "/sagex/media/poster/" + dbidTmp
            
            ATVBody_sR_m_s_mS_i_tLEMI_dI = etree.SubElement(ATVBody_sR_m_s_mS_i_tLEMI, 'defaultImage')
            ATVBody_sR_m_s_mS_i_tLEMI_dI.text = "resource://Poster.png"


#    ATVBody_sR_m_s_mS_i_tLEMI = etree.SubElement(ATVBody_sR_m_s_mS_i, 'twoLineEnhancedMenuItem')
#    ATVBody_sR_m_s_mS_i_tLEMI.set('id','tLEMI_1')
#
#    txtTmp = "atv.loadURL('http://" + stv_cnct_ip + "')"
#    MediaIdValue = "11128704"
#
#    ATVBody_sR_m_s_mS_i_tLEMI.set('onPlay', txtTmp + "/MediaId=" + MediaIdValue )
#    ATVBody_sR_m_s_mS_i_tLEMI.set('onSelect', txtTmp + "/MediaFileId=" + MediaIdValue )
#    ATVBody_sR_m_s_mS_i_tLEMI.set('onHoldSelect', txtTmp + "/MediaFileId=" + MediaIdValue )
#
#    ATVBody_sR_m_s_mS_i_tLEMI_l = etree.SubElement(ATVBody_sR_m_s_mS_i_tLEMI, 'label')
#    ATVBody_sR_m_s_mS_i_tLEMI_l.text = "Label2"
#    ATVBody_sR_m_s_mS_i_tLEMI_i = etree.SubElement(ATVBody_sR_m_s_mS_i_tLEMI, 'image')
#    ATVBody_sR_m_s_mS_i_tLEMI_i.text = "http://" + stv_cnct_ip + "/stream/MediaFileThumbnailServlet?MediaFileId=" + MediaIdValue
#    ATVBody_sR_m_s_mS_i_tLEMI_dI = etree.SubElement(ATVBody_sR_m_s_mS_i_tLEMI, 'defaultImage')
#    ATVBody_sR_m_s_mS_i_tLEMI_dI.text = "resource://Poster.png"

    return ATVRoot

def setTimeline(path):
    # find sageDbId
    # find time
    # save "time" into a file called sageDbId

    # 00:14:12 WebServer: serving .xml: /:/timeline :
    #?ratingKey=undefined
    #&duration=undefined
    #&key=%2Flibrary%2Fmetadata%2Fundefined
    #&state=play
    #&time=0
    #&report=1
    #&sageDbId=11031928
    #&X-Plex-Client-Identifier=C07FDV4EDDR5
    #&X-Plex-Device-Name=Family%20Room%20Apple%20TV

    sageDbId = path[path.find("sageDbId="):]
    sageDbId = sageDbId[sageDbId.find('=') + 1 :sageDbId.find('&')]

    time = path[path.find("time="):]
    time = time[time.find('=') + 1 :time.find('&')]

    # if the dir does not exist, make it
    if not os.path.exists("bookmarks"):
        os.makedirs("bookmarks")
        
    file = codecs.open("bookmarks/" + sageDbId + ".bk", "w", "utf-8")
    file.write(time)
    file.close()

    return


def makeExample(path):
    dprint(__name__, 1, "====== makeExample ======: {0}", path)

    if path[path.rfind('=')+1:] is "":
        filename = "mainmenu.xml"

    else:
        filename = path[path.rfind('=')+1:]

    print "name--> " + filename
    filename = "examples/" + filename

    print "name--> " + filename
    file = codecs.open(filename, "r", "utf-8")
    textXML = file.read()
    file.close()


    tree = etree.fromstring(textXML)

    return tree

    # Display a list of example screens
    # load static example file
    # return xml as appropriate

    # default, top menu
    # viewWithNavigatorBar
    # scroller - grid / collection divider
    # scrollerPreview
    # itemDetail
    # listWithPreview - twoLineEnhancedItem
    # listWithPreview - oneLineMenuItem  preview / cross fade preview
    # listWithPreview - twoLineMenuItem  preview / cross fade preview
    #                    horizontalDivider
    #                    rightLabel
    #       When an item is selected, the url needs to be
    #           a scrollerPreview? (or other type?)
    #unplayedDot
    # plist -- audio play list?
    # mediabrowser - header with count and buttons
    # videoplayer (cant actually show)
    # dialog
    # preview - paradepreview
    # Search
    # searchResults
    # listScrollerSplit

#def getTrailersMenu():
#
# Main drop down
#
#http://trailers.apple.com/appletv/index.xml
#https://trailers.apple.com/appletv/browse.xml
#https://trailers.apple.com/appletv/genres/am/index.xml
#https://trailers.apple.com/appletv/genres/nz/index.xml
#
#    grid
#    browse
#    Showtimes
#    search


def getTrailers(path, bin, headers):
    dprint(__name__, 1, "====== getTrailers ======: {0}", path )
    #
    # Call out to Apple, get the appropriate page, return it
    #
    # get address, path with auth and xml=yes
    #r = requests.get(address + path, auth=(username, password))
#    r = requests.get( textURL , auth=(username, password))

    # https://trailers.apple.com/trailers/independent/freebirds/images/poster-xlarge.jpg


    #User-Agent: iTunes-AppleTV/5.3 (2; 8GB; dt:11)
#    headers = {'User-Agent': 'iTunes-AppleTV/5.3 (2; 8GB; dt:11)'}


    r = requests.get( "http://trailers.apple.com" + path , headers=headers )
    
    if int(r.status_code) == 200:
        dprint(__name__, 2, "code 200")
        dprint(__name__, 2, "encoding: {0}", r.encoding )
        #        r.encoding = 'ucs-2'
        #        dprint(__name__, 2, "encoding: {0}", r.encoding )
        
        #        root = etree.fromstring(r.text.encode('utf-8'))
        
        if bin == "True":
            return r.content
        else:
#            print r.text.encode('utf-8')
            return r.text.encode('utf-8')

    elif ( int(r.status_code) == 301 ) or ( int(r.status_code) == 302 ):
        dprint(__name__, 0, "headers: {0}", r.headers.get('Location') )
        return r.text.encode('utf-8')
    
    elif int(r.status_code) >= 400:
        error = "HTTP response error: " + str(r.status_code) + " " + str(r.text)
        dprint(__name__, 0, "error: {0}", error )
        return r.text.encode('utf-8')

    return


#
# Query the SageTv server and get a list of all eppisodes
# for the selected show
#
def makeChannelList():
    dprint(__name__, 1, "====== makeChannelList ======" )
    InitCfg()
    
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
    
    textURL = "/sagex/api?c=GetAllChannels"
    textURL = "http://" + username + ":" + password + "@" + sagetv_ip + textURL
    dprint(__name__, 2, "--> {0}", textURL )


    # http://sagetv.ursaminor.net/sage/ChannelLogo?ChannelID=12852&type=Sm&index=1&fallback=true


    # non-Working Sagex api calls :(
    # http://sagetv.ursaminor.net/sagex/api?c=GetAllChannels
    # http://sagetv.ursaminor.net/sagex/api?c=GetChannelForStationID&1=10093
#    <Result size="50">
#        <Channel>
#            <ChannelDescription>
#                <![CDATA[ ABC Family ]]>
#            </ChannelDescription>
#            <ChannelName>
#                <![CDATA[ ABCF ]]>
#            </ChannelName>
#            <ChannelNetwork>
#                <![CDATA[ Satellite ]]>
#            </ChannelNetwork>
#            <ChannelNumber>
#                <![CDATA[ 1700 ]]>
#            </ChannelNumber>
#            <IsChannelViewable>false</IsChannelViewable>
#            <StationID>10093</StationID>
#            <IsChannelObject>true</IsChannelObject>
#            <ChannelLogoCount>2</ChannelLogoCount>
#        </Channel>


    #<atv>
    #    <head>
    #        <script src="{{URL(:/js/utils.js)}}" />
    #    </head>
    ATVRoot = etree.Element("atv")
    ATVHead = etree.SubElement(ATVRoot, 'head')
    ATVtemp = etree.SubElement(ATVHead, 'script')
    ATVtemp.set('src',"http://" + stv_cnct_ip + "/home/tv/PlexConnect/assets/js/utils.js")
    
    
    #	<body>
    #		<listScrollerSplit id="com.sample.list-scroller-split">
    ATVBody = etree.SubElement(ATVRoot, 'body')
    
    #    ATVLSS = etree.SubElement(ATVBody, 'optionDialog') # Centered and Centered!
    #    ATVLSS.set('id', "com.sample.movie-grid")
    
    
    ATVLSS = etree.SubElement(ATVBody, 'listScrollerSplit') # Centered and Centered!
    ATVLSS.set('id', "com.menu.Main.list-scroller-split")
    ##    ATVListWPreview.set('volatile', "true")
    ##    ATVListWPreview.set('onVolatileReload', "atv.loadAndSwapURL('http://" + stv_cnct_ip  + "/SageConnect.xml')")
    
    #<header>
    #    <simpleHeader>
    #        <title>Movie Trailers</title>
    #        <subtitle>SubTitle</subtitle>
    #    </simpleHeader>
    #</header>
    ATV_LSS_M_H = etree.SubElement(ATVLSS, 'header')
    ATV_LSS_M_H_sH = etree.SubElement(ATV_LSS_M_H, 'simpleHeader')
    ATV_LSS_M_H_sH_t = etree.SubElement(ATV_LSS_M_H_sH, 'title')
    titleText = atvTitle[atvTitle.find('=')+1:]
    titleText = titleText.replace('+',' ')
    titleText = unquote_plus(titleText)
    ATV_LSS_M_H_sH_t.text = titleText
    #    ATV_LSS_M_H_sH_t = etree.SubElement(ATV_LSS_M_H_sH, 'subtitle')
    #    ATV_LSS_M_H_sH_t.text = "Current Episodes"
    
    
    #        <menu>
    #            <sections>
    #                <menuSection>
    #                   <items>
    ATV_LSS_Menu = etree.SubElement(ATVLSS, 'menu')
    ATV_LSS_Sections = etree.SubElement(ATV_LSS_Menu, 'sections')
    ATV_LSS_MenuSections = etree.SubElement(ATV_LSS_Sections, 'menuSection')
    
    
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
                        
                        #                        ## delete this
                        #                        href = "{var ev = ''; var out = [];for (ev in window){if (/^on/.test(ev)) {out[out.length] = ev;}}log(out.join(', '));};" + href
                        
                        
                        dprint(__name__, 2, "---- href ---> {0}", href )
                        
                        # Get the show name
                        mediaId = title.find('input')
                        if mediaId is not None:
                            mediaId = mediaId.get('value')
                        else:
                            mediaId = ""
                        
                        
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
                        
                        if eps.text is not None:
                            if eps.text.find(".") > 0:
                                if eps.text.find("GB") < 0:
                                    if eps.text.find("MB") < 0:
                                        # this is the episode description
                                        episodeDesc = eps.text
                        
                        if eps.text is not None and eps.text.find(":") > 0:
                            # this is the original airing time
                            episodeDate = eps.text
                        # grab just the airing date (remove day and time)
                        #                            episodeDate = episodeDate[episodeDate.find(',') + 1:]
                        #                            episodeDate = episodeDate[:episodeDate.rfind(',')]
                        #                            episodeDate = episodeDate.strip()
                        
                        if eps.find('img') is not None:
                            # these are the images that tell view status
                            img = ""
                    
                    
                    # make sure that something is in the title even if its just the show name
                    if episodeTitle == "":
                        episodeTitle = showTitle
                    
                    
                    
                    
                    
                    # Repeat for each item in the list
                    #<items>
                    #    <twoLineEnhancedMenuItem id="1a"
                    #        onPlay="atv.loadURL('http://SageConnect.Server/exampleLayouts=scroller.xml')"
                    #        onSelect="atv.loadURL('http://SageConnect.Server/exampleLayouts=scroller.xml')">
                    #        <label>TV</label>
                    #        <label2>Recorded Television</label2>
                    #        <image>http://SageConnect.Server/thumbnails/TvIcon.png</image>
                    #        <!--<defaultImage>resource://Poster.png</defaultImage>-->
                    #        <preview>
                    #            <keyedPreview>
                    #                <title>Recorded Television</title>
                    #                <summary>27 Shows (285 Recordings)</summary>
                    #                <image>http://SageConnect.Server/thumbnails/SageTVLogo.jpg</image>
                    #            </keyedPreview>
                    #        </preview>
                    #    </twoLineEnhancedMenuItem>
                    #</items>
                    
                    
                    #
                    # Add Generic SageTV item.... use this to show current status
                    #
                    href = "http://" + stv_cnct_ip + "/MediaId.xml="
                    hdrhref = "atv.loadURL('" + href + mediaId + "')"
                    ATV_LSS_MS_I_Item = etree.SubElement(ATV_LSS_MS_Items, 'oneLineMenuItem')
                    ATV_LSS_MS_I_Item.set("id", episodeTitle )
                    ATV_LSS_MS_I_Item.set("onPlay", hdrhref )
                    ATV_LSS_MS_I_Item.set("onSelect", hdrhref )
                    ATV_LSS_MS_I_ItemLabel = etree.SubElement(ATV_LSS_MS_I_Item, 'label')
                    ATV_LSS_MS_I_ItemLabel.text = episodeTitle
                    #                    ATV_LSS_MS_I_ItemImg = etree.SubElement(ATV_LSS_MS_I_Item, 'image')
                    ##                    ATV_LSS_MS_I_ItemImg.text = "http://" + stv_cnct_ip + "/thumbnails/Ball.png"
                    #                    ATV_LSS_MS_I_ItemImg = etree.SubElement(ATV_LSS_MS_I_Item, 'defaultImage')
                    ATV_LSS_MS_I_ItemPrev = etree.SubElement(ATV_LSS_MS_I_Item, 'preview')
                    ATV_LSS_MS_I_ItemKP = etree.SubElement(ATV_LSS_MS_I_ItemPrev, 'keyedPreview')
                    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'title')
                    ATV_LSS_MS_I_ItemKP_x.text = episodeTitle
                    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'summary')
                    if episodeDesc <> "":
                        ATV_LSS_MS_I_ItemKP_x.text = episodeDesc
                    
                    # The image tag is required, but can be empty
                    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'image')
                    ATV_LSS_MS_I_ItemKP_x.text = "http://" + sagetv_ip + "/stream/MediaFileThumbnailServlet?MediaFileId=" + mediaId
                    
                    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'metadataKeys')
                    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
                    ATV_LSS_MS_I_ItemKP_xy.text = "Recorded"
                    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
                    ATV_LSS_MS_I_ItemKP_xy.text = "Duration"
                    
                    ATV_LSS_MS_I_ItemKP_x = etree.SubElement(ATV_LSS_MS_I_ItemKP, 'metadataValues')
                    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
                    ATV_LSS_MS_I_ItemKP_xy.text = episodeDate
                    ATV_LSS_MS_I_ItemKP_xy = etree.SubElement(ATV_LSS_MS_I_ItemKP_x, 'label')
                    ATV_LSS_MS_I_ItemKP_xy.text = "20 M"
    
    
    return ATVRoot



"""
    # XML converter functions
    # - translate aTV request and send to PMS
    # - receive reply from PMS
    # - select XML template
    # - translate to aTV XML
    """
def XML_STV2aTV(address, path, options, headers):
    
    # OnScreen tree ends up as
    #    Top menu
    #        Recorded Shows (title List)
    #            Titles (List all episodes in that title)
    #                Episode / Airing ID INFO
    #                    Make "play" xml using Media ID
    #        Media directories
    #            Sub dirs
    #                Media files
    #                    make play XML using SageDBID
    
    #
    # I cheated, to "remove" spaces in URLs, I made them *
    # so replace all '*' with ' '
    # There is probably a "correct" way to do this.. I'll have to look into this.
    #
    dprint(__name__, 1, "--path-----> {0}", path)
    path = path.replace('+',' ')
    path = path.replace('&apos;','\'')
    # for now, we are ignoring the address passed
    #    print "--address--> " + address
    dprint(__name__, 1, "--path-----> {0}", path)
    
    # Make top menu
    if path.find("SageConnect") > 0:
        aTVroot = makeTopMenu()
        return etree.tostring(aTVroot)
    
    #========== Display example layouts ===========
    # Make and return a list of all recorded shows
    elif path.find("exampleLayouts=") > 0:
        aTVroot = makeExample(path)
        return etree.tostring(aTVroot)
    
    #========== Handle / Manage recorded shows ===========
    # Make and return a list of all recorded shows
    elif path.find("recordedShows") > 0:
        aTVroot = makeRecordedShowList()
        return etree.tostring(aTVroot)
    
    # Make and return a list of all recorded shows
    elif path.find("recordedGrid") > 0:
        aTVroot = makeTitleGrid(path)
        return etree.tostring(aTVroot)
    
    # if given a show title, make a list of all episodes
    elif path.find("title") > 0:
        aTVroot = makeShowList(path)
        return etree.tostring(aTVroot)
    
    # if given a media id, get media info and display on screen
    elif path.find("MediaId") > 0:
        aTVroot = makeMediaInfo(path)
        return etree.tostring(aTVroot)
    
    # when play is clicked, return the XML with media info
    elif path.find("MediaFileId") > 0:
        aTVroot = makePlay(path)
        return etree.tostring(aTVroot)
    
    #========== Handle / Manage media library ===========
    
    # if MediaLibrary.... make show list
    # parse and return the media path
    # if this is a media file, return the XML similar to MediaID above
    # when play is clicked, MediaFileID (above) is called
    # parse the path to get what to generate
    elif path.find("mediaPath") > 0:
        aTVroot = makeDirList(path[path.find('=')+1:])
        return etree.tostring(aTVroot)
    
    #========== Search ===========
    
    # when search main is requested
    elif path.find("mediaSearch") > 0:
        aTVroot = searchTitle()
        return etree.tostring(aTVroot)
    
    # when a search query comes through
    elif path.find("search?") > 0:
        aTVroot = searchMedia(path)
        return etree.tostring(aTVroot)
    
    #========== Playtime Feedback (for resume) ===========
    
    # when search main is requested
    elif path.find("timeline") > 0:
        setTimeline(path)
        return

    #========== Make Apple Trailers Work ===========
    # https://trailers.apple.com/trailers/independent/freebirds/images/poster-xlarge.jpg
    # Make and return a list of all recorded shows
    elif path.startswith("/appletv/"):
        return getTrailers(path, "false", headers)

    elif path.startswith("/trailers/"):
        return getTrailers(path, "false", headers)

    # Generate an error
    return XML_Error('SageTV Connect', 'Unable to handle request, please try again.')


def InitCfg():
    cfg = Settings.CSettings()
    param = {}
    param['CSettings'] = cfg

    param['Addr_PMS'] = '*Addr_PMS*'
    param['HostToIntercept'] = 'trailers.apple.com'
    setParams(param)

    cfg = ATVSettings.CATVSettings()
    setATVSettings(cfg)
    return

if __name__=="__main__":
    print "SageXML Main"
    InitCfg()
    
