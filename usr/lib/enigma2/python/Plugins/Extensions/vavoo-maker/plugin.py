#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
#########################################################
#                                                       #
#  Vavoo Maker Playlists Plugin                         #
#  Version: 1.2                                         #
#  Created by Lululla (https://github.com/Belfagor2005) #
#  License: CC BY-NC-SA 4.0                             #
#  https://creativecommons.org/licenses/by-nc-sa/4.0    #
#  Last Modified: 20251119                              #
#                                                       #
#  Credits:                                             #
#  - Original concept by Lululla                        #
#  - Special thanks to @Warder for testing              #
#  - Linuxsat-support.com & Corvoboys communities       #
#                                                       #
#  Usage of this code without proper attribution        #
#  is strictly prohibited.                              #
#  For modifications and redistribution,                #
#  please maintain this credit header.                  #
#########################################################
"""

__author__ = "Lululla"
__version__ = "1.2"
__license__ = "CC BY-NC-SA 4.0"
__credits__ = ["Linuxsat-support.com", "Corvoboys Forum"]
__maintainer__ = "Lululla"
__email__ = "https://github.com/Belfagor2005"
__status__ = "Production"

# =========================
# Standard library imports
# =========================
import json
import codecs
from time import time
from sys import version_info
from os import (
    listdir as os_listdir,
    makedirs as os_makedirs,
    path as os_path,
    remove as os_remove,
)
from shutil import rmtree

# =========================
# Third-party imports
# =========================
from requests import get, exceptions

# =========================
# Enigma2 / Plugins imports
# =========================
from enigma import eTimer
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.config import (
    config,
    ConfigSubsection,
    ConfigSelection,
    ConfigText,
    configfile,
)
from Components.MenuList import MenuList
from Plugins.Plugin import PluginDescriptor
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.Directories import SCOPE_PLUGINS, resolveFilename

# =========================
# Conditional imports
# =========================
if os_path.exists("/usr/bin/apt-get"):
    from .SelDMList import SelectionList, SelectionEntryComponent
    base_class = Screen
else:
    from .SelList import SelectionList, SelectionEntryComponent
    from Screens.Screen import Screen, ScreenSummary
    base_class = ScreenSummary

# =========================
# Local package imports
# =========================
from . import (
    _,
    group_titles,
    reload_bouquet,
    unquote,
    pickle,
)

from .vavoo_lib import (
    sanitizeFilename,
    getAuthSignature,
    decodeHtml,
    rimuovi_parentesi,
)

tempDir = "/tmp/vavoo"
if not os_path.exists(tempDir):
    os_makedirs(tempDir)

PLUGIN_PATH = resolveFilename(SCOPE_PLUGINS, "Extensions/{}".format('vavoo-maker'))
config.plugins.vavoomaker = ConfigSubsection()
config.plugins.vavoomaker = ConfigSubsection()
choices = {
    "country": _("Countries"),
    "categories": _("Categories")
}
config.plugins.vavoomaker.current = ConfigSelection(
    choices=[(x[0], x[1]) for x in choices.items()],
    default=list(choices.keys())[0]
)
for ch in choices:
    setattr(config.plugins.vavoomaker, ch, ConfigText("", False))


PYTHON_VER = version_info.major


class vavooFetcher():
    def __init__(self):

        self.tempDir = "/tmp/vavoo"
        if not os_path.exists(self.tempDir):
            os_makedirs(self.tempDir)

        self.cachefile = os_path.join(self.tempDir, "vavoo.cache")
        self.playlists = {
            "country": "https://vavoo.to/channels",
            "countries": "https://vavoo.to/channels",
            "categories": "https://vavoo.to/channels"
        }
        self.bouquetFilename = "userbouquet.vavoo.%s.tv"
        self.bouquetName = _("vavoo")
        self.playlists_processed = {key: {} for key in self.playlists.keys()}
        self.cache_updated = False
        if os_path.exists(self.cachefile):
            try:
                mtime = os_path.getmtime(self.cachefile)
                if mtime < time() - 86400:  # if file is older than one day delete it
                    os_remove(self.cachefile)
                else:
                    with open(self.cachefile, 'rb') as cache_input:
                        self.playlists_processed = pickle.load(cache_input)
            except Exception as e:
                print("[vavoo plugin] failed to open cache file", e)

    def downloadPage(self):
        link = self.playlists[config.plugins.vavoomaker.current.value]
        try:
            response = get(link, timeout=2.50)
            response.raise_for_status()
            with open(self.tempDir + "/" + config.plugins.vavoomaker.current.value, "wb") as f:
                f.write(response.content)
        except exceptions.RequestException as error:
            print("[vavoo plugin] failed to download", link)
            print("[vavoo plugin] error", str(error))

    def getPlaylist(self):
        current = self.playlists_processed.get(config.plugins.vavoomaker.current.value, {})
        if not current:
            self.downloadPage()

        known_urls = []
        json_data = os_path.join(self.tempDir, config.plugins.vavoomaker.current.value)

        try:
            if os_path.exists(json_data):
                with codecs.open(json_data, "r", "utf-8") as f:
                    playlist = json.load(f)
            else:
                print("File JSON not found:", json_data)
                return

        except Exception as e:
            print("Error on parsing JSON:", e)
            playlist = []

        if isinstance(playlist, dict):
            playlist = [playlist]

        for entry in playlist:
            if not isinstance(entry, dict):
                print("no valid format:", entry)
                continue

            country = unquote(entry.get("country", "")).strip("\r\n")
            name = unquote(entry.get("name", "")).strip("\r\n")
            name = decodeHtml(name)
            name = rimuovi_parentesi(name)
            ids = str(entry.get("id", "")).replace(":", "").replace(" ", "").replace(",", "")

            if not country or not name or not ids:
                print("Missing data in entry:", entry)
                continue

            url = "https://vavoo.to/live2/play/" + ids + ".ts"

            if url not in known_urls:
                if country not in current:
                    current[country] = []
                current[country].append((name, url))
                known_urls.append(url)

        self.cache_updated = True

    def createBouquet(self, enabled):
        sig = getAuthSignature()
        app = '?n=1&b=5&vavoo_auth=%s#User-Agent=VAVOO/2.6' % (str(sig))
        current = self.playlists_processed[config.plugins.vavoomaker.current.value]

        def bouquet_exists(bouquets_file, bouquet_entry):
            """Check if bouquet is already in main list"""
            if os_path.exists(bouquets_file):
                with open(bouquets_file, "r") as f:
                    return bouquet_entry in f.read()
            return False

        for country in sorted([k for k in current.keys() if k in enabled], key=lambda x: group_titles.get(x, x).lower()):
            bouquet_list = []
            if current[country]:
                bouquet_list.append("#NAME %s" % group_titles.get(country, country))

                for channelname, url in sorted(current[country]):
                    clean_url = url.strip() + str(app)
                    encoded_url = clean_url.replace(":", "%3a")
                    bouquet_list.append("#SERVICE 4097:0:1:1:1:1:CCCC0000:0:0:0:%s:%s" % (encoded_url, channelname))

            if bouquet_list:
                bouquet_filename = "userbouquet.vavoo.%s.tv" % sanitizeFilename(country).replace(" ", "_").strip().lower()
                bouquet_path = os_path.join("/etc/enigma2", bouquet_filename)

                try:
                    content = "\n".join(bouquet_list)
                    with open(bouquet_path, "w") as f:
                        if not PYTHON_VER == 3:
                            f.write(content.encode('utf-8'))
                        else:
                            f.write(content)
                except Exception as e:
                    print("Error writing bouquet:", str(e))
                    continue

            bouquets_file = "/etc/enigma2/bouquets.tv"
            bouquet_entry = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet\n' % bouquet_filename

            if not bouquet_exists(bouquets_file, bouquet_entry):
                try:
                    with open(bouquets_file, "a") as f:
                        f.write(bouquet_entry)
                except Exception as e:
                    print("Error updating bouquets.tv:", str(e))

        reload_bouquet()

    def removeBouquetReference(self, bouquet_filename):
        bouquets_file = "/etc/enigma2/bouquets.tv"

        if os_path.exists(bouquets_file):
            try:
                with open(bouquets_file, "r") as f:
                    lines = f.readlines()

                with open(bouquets_file, "w") as f:
                    for line in lines:
                        if bouquet_filename.lower() not in line.lower():
                            f.write(line)

                print("[vavoo plugin] Bouquet entry removed from bouquets.tv:", bouquet_filename)
            except Exception as e:
                print("[vavoo plugin] Error updating bouquets.tv:", e)

    def removeBouquet(self, enabled):
        current = self.playlists_processed[config.plugins.vavoomaker.current.value]
        for country in sorted([k for k in current.keys() if k in enabled], key=lambda x: group_titles.get(x, x).lower()):
            if current[country]:
                bouquet_filename = sanitizeFilename(country).replace(" ", "_").strip().lower()
                bouquet_name = "userbouquet.vavoo.%s.tv" % bouquet_filename
                bouquet_path = os_path.join("/etc/enigma2", bouquet_name)

                if os_path.exists(bouquet_path):
                    print("[vavoo plugin] Removing bouquet:", bouquet_name)
                    try:
                        os_remove(bouquet_path)  # Directly remove the bouquet file
                        self.removeBouquetReference(bouquet_name)
                        print("[vavoo plugin] Bouquet removed:", bouquet_name)
                    except Exception as e:
                        print("[vavoo plugin] Error removing bouquet:", bouquet_name, e)
                else:
                    print("[vavoo plugin] Bouquet does not exist:", bouquet_name)

        reload_bouquet()

    def removeAllVavooBouquets(self):
        """
        Clean up routine to remove any previously made changes
        """
        bouquet_dir = "/etc/enigma2"
        bouquets_file = os_path.join(bouquet_dir, "bouquets.tv")
        removed_bouquets = []

        for file in os_listdir(bouquet_dir):
            if file.startswith("userbouquet.vavoo") and file.endswith(".tv"):
                bouquet_path = os_path.join(bouquet_dir, file)
                removed_bouquets.append(file)

                if os_path.exists(bouquet_path):
                    print("[vavoo plugin] Removing bouquet:", file)
                    try:
                        os_remove(bouquet_path)
                        print("[vavoo plugin] Bouquet removed:", file)
                    except Exception as e:
                        print("[vavoo plugin] Error removing bouquet:", file, e)
                else:
                    print("[vavoo plugin] Bouquet does not exist:", file)

        if os_path.exists(bouquets_file) and removed_bouquets:
            try:
                with open(bouquets_file, "r") as f:
                    lines = f.readlines()

                with open(bouquets_file, "w") as f:
                    for line in lines:
                        if not any(bouquet.lower() in line.lower() for bouquet in removed_bouquets):
                            f.write(line)
                print("[vavoo plugin] Removed references from bouquets.tv")
            except Exception as e:
                print("[vavoo plugin] Error updating bouquets.tv:", e)

        reload_bouquet()

    def cleanup(self):
        rmtree(self.tempDir)
        if self.cache_updated:
            with open(self.cachefile, 'wb') as cache_output:
                pickle.dump(self.playlists_processed, cache_output, pickle.HIGHEST_PROTOCOL)


class SetupMaker(Screen):
    if os_path.exists("/usr/bin/apt-get"):
        skin = '''
            <screen name="SetupMaker" position="center,center" size="1920,1080" title="SetupMaker" backgroundColor="transparent" flags="wfNoBorder">
                <eLabel backgroundColor="#002d3d5b" cornerRadius="20" position="19,22" size="1255,711" zPosition="-99" />
                <eLabel name="" position="31,30" size="1220,683" zPosition="-90" cornerRadius="18" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                <!-- /* time -->
                <eLabel name="" position="30,34" size="700,52" backgroundColor="#00171a1c" halign="center" valign="center" transparent="0" font="Regular; 36" zPosition="1" text="VAVOO MAKER BY LULULLA" foregroundColor="#007fcfff" />
                <widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="1107,40" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="120,40" source="global.CurrentTime" transparent="1" zPosition="3">
                    <convert type="ClockToText">Default</convert>
                </widget>
                <widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="731,38" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="400,40" source="global.CurrentTime" transparent="1" zPosition="3">
                    <convert type="ClockToText">Date</convert>
                </widget>
               
                <eLabel name="" position="22,30" size="1244,690" zPosition="-90" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                <eLabel backgroundColor="#001a2336" position="34,90" size="1220,3" zPosition="10" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="619,386" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="619,434" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_yellow.png" position="620,486" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_blue.png" position="620,534" size="30,30" alphatest="blend" transparent="1" />
                <widget backgroundColor="#9f1313" font="Regular;30" halign="left" position="660,380" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="1" />
                <widget backgroundColor="#1f771f" font="Regular;30" halign="left" position="660,430" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="1" />
                <widget backgroundColor="#a08500" font="Regular;30" halign="left" position="660,480" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_yellow" transparent="1" valign="center" zPosition="1" />
                <widget backgroundColor="#18188b" font="Regular;30" halign="left" position="661,530" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_blue" transparent="1" valign="center" zPosition="1" />
                <widget name="config" position="40,100" size="550,585" itemHeight="35" enableWrapAround="1" transparent="0" zPosition="9" scrollbarMode="showOnDemand" />
                <widget name="description" position="610,604" size="635,81" font="Regular; 32" halign="center" foregroundColor="#00ffffff" transparent="1" zPosition="3" />
                <eLabel backgroundColor="#00fffffe" position="35,695" size="1200,3" zPosition="10" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/log.png" position="616,109" size="512,256" zPosition="5" />
                <widget source="session.CurrentService" render="Label" position="915,561" size="350,34" font="Regular;26" borderWidth="1" backgroundColor="background" transparent="1" halign="center" foregroundColor="white" zPosition="30" valign="center" noWrap="1">
                    <convert type="ServiceName">Name</convert>
                </widget>
                <widget source="session.VideoPicture" render="Pig" position="936,375" zPosition="20" size="300,180" backgroundColor="transparent" transparent="0" cornerRadius="14" />
            </screen>
            '''

    else:
        skin = '''
            <screen name="SetupMaker" position="center,center" size="1920,1080" title="SetupMaker" backgroundColor="transparent" flags="wfNoBorder">
                <eLabel backgroundColor="#002d3d5b" cornerRadius="20" position="19,22" size="1255,711" zPosition="-99" />
                <eLabel name="" position="31,30" size="1220,683" zPosition="-90" cornerRadius="18" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                <!-- /* time -->
                <eLabel name="" position="30,34" size="700,52" backgroundColor="#00171a1c" halign="center" valign="center" transparent="0" font="Regular; 36" zPosition="1" text="VAVOO MAKER BY LULULLA" foregroundColor="#007fcfff" />
                <widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="1107,40" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="120,40" source="global.CurrentTime" transparent="1" zPosition="3">
                    <convert type="ClockToText">Default</convert>
                </widget>
                <widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="731,38" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="400,40" source="global.CurrentTime" transparent="1" zPosition="3">
                    <convert type="ClockToText">Date</convert>
                </widget>
               
                <eLabel name="" position="22,30" size="1244,690" zPosition="-90" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                <eLabel backgroundColor="#001a2336" position="34,90" size="1220,3" zPosition="10" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="619,386" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="619,434" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_yellow.png" position="620,486" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_blue.png" position="620,534" size="30,30" alphatest="blend" transparent="1" />
                <widget backgroundColor="#9f1313" font="Regular;30" halign="left" position="660,380" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="1" />
                <widget backgroundColor="#1f771f" font="Regular;30" halign="left" position="660,430" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="1" />
                <widget backgroundColor="#a08500" font="Regular;30" halign="left" position="660,480" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_yellow" transparent="1" valign="center" zPosition="1" />
                <widget backgroundColor="#18188b" font="Regular;30" halign="left" position="661,530" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_blue" transparent="1" valign="center" zPosition="1" />
                <widget name="config" position="40,100" size="550,585" itemHeight="35" font="Regular; 30" enableWrapAround="1" transparent="0" zPosition="9" scrollbarMode="showOnDemand" />
                <widget name="description" position="610,604" size="635,81" font="Regular; 32" halign="center" foregroundColor="#00ffffff" transparent="1" zPosition="3" />
                <eLabel backgroundColor="#00fffffe" position="35,695" size="1200,3" zPosition="10" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/log.png" position="616,109" size="512,256" zPosition="5" />
                <widget source="session.CurrentService" render="Label" position="915,561" size="350,34" font="Regular;26" borderWidth="1" backgroundColor="background" transparent="1" halign="center" foregroundColor="white" zPosition="30" valign="center" noWrap="1">
                    <convert type="ServiceName">Name</convert>
                </widget>
                <widget source="session.VideoPicture" render="Pig" position="936,375" zPosition="20" size="300,180" backgroundColor="transparent" transparent="0" cornerRadius="14" />
            </screen>
            '''

    def __init__(self, session, view_type=None):
        Screen.__init__(self, session)
        # self.skin = ctrlSkin('SetupMaker', SetupMaker.skin)
        self.view_type = view_type or config.plugins.vavoomaker.current.value

        self.title = _("vavoo playlists") + " - " + choices.get(self.view_type, self.view_type).title()
        self.enabled = []
        self.process_build = []
        self.vavooFetcher = vavooFetcher()
        self["description"] = StaticText(_("Downloading playlist - Please wait!"))
        self["config"] = SelectionList([], enableWrapAround=True)
        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText()
        self["key_yellow"] = StaticText()
        self["key_blue"] = StaticText(_("Remove"))
        self["actions"] = ActionMap(
            [
                "SetupActions",
                "ColorActions",
                "OkCancelActions"
            ],
            {
                "ok": self["config"].toggleSelection,
                "green": self.makeBouquets,
                "save": self.makeBouquets,
                "cancel": self.backCancel,
                "red":  self.backCancel,
                "yellow": self["config"].toggleAllSelection,
                "blue": self.deleteBouquets,
            },
            -2
        )

        self.timer = eTimer()
        if hasattr(self.timer, "callback"):
            self.timer.callback.append(self.buildList)
        else:
            if os_path.exists("/usr/bin/apt-get"):
                self.timer_conn = self.timer.timeout.connect(self.buildList)
            print("[Version Check] ERROR: eTimer does not support callback.append()")
        self.timer.start(10, 1)

        self.onClose.append(self.__onClose)

    def __onClose(self):
        try:
            self.vavooFetcher.cleanup()
        except Exception as e:
            print('Error clean:', e)
            pass

    def buildList(self):
        self["actions"].setEnabled(False)
        self.vavooFetcher.getPlaylist()
        all_items = list(self.vavooFetcher.playlists_processed[config.plugins.vavoomaker.current.value].keys())
        if self.view_type == "countries":
            self.process_build = [x for x in all_items if "➾" not in x and "⟾" not in x and "->" not in x]
        elif self.view_type == "categories":
            self.process_build = [x for x in all_items if "➾" in x or "⟾" in x or "->" in x]
        else:
            self.process_build = all_items

        self.process_build = sorted(self.process_build, key=lambda x: group_titles.get(x, x).lower())
        self.enabled = [x for x in getattr(config.plugins.vavoomaker, config.plugins.vavoomaker.current.value).value.split("|") if x in self.process_build]
        self["config"].setList([SelectionEntryComponent(group_titles.get(x, x), x, "", x in self.enabled) for x in self.process_build])
        self["actions"].setEnabled(True)
        self["key_green"].setText(_("Create bouquets"))
        self["key_yellow"].setText(_("Toggle all"))
        self["description"].setText(_("Select Items for Export"))

    def readList(self):
        self.enabled = [x[0][1] for x in self["config"].list if x[0][3]]
        getattr(config.plugins.vavoomaker, config.plugins.vavoomaker.current.value).value = "|".join(self.enabled)

    def makeBouquets(self):

        def onConfirm(answer):
            if answer:
                self.readList()
                if self.enabled:
                    # self["actions"].setEnabled(False)
                    self.title += " - " + _("Creating bouquets")
                    self["description"].text = _("Creating bouquets. This may take some time. Please be patient.")
                    self["key_red"].text = ""
                    self["key_green"].text = ""
                    self["key_yellow"].text = ""
                    self["key_blue"].text = ""
                    self["config"].setList([])
                    config.plugins.vavoomaker.current.save()
                    for ch in choices:
                        getattr(config.plugins.vavoomaker, ch).save()
                    configfile.save()
                    self.runtimer = eTimer()
                    if hasattr(self.runtimer, "callback"):
                        self.runtimer.callback.append(self.doRun)
                    else:
                        if os_path.exists("/usr/bin/apt-get"):
                            self.runtimer_conn = self.runtimer.timeout.connect(self.doRun)
                        print("[Version Check] ERROR: eTimer does not support callback.append()")
                    self.runtimer.start(10, 1)
                else:
                    self.session.open(MessageBox, _("Please select the bouquets you wish to create."), MessageBox.TYPE_INFO, timeout=5)

        self.session.openWithCallback(
            onConfirm,
            MessageBox,
            _("Do you want to create the bouquets?"),
            MessageBox.TYPE_YESNO,
            timeout=10,
            default=True
        )

    def doRun(self):
        self.vavooFetcher.createBouquet(self.enabled)
        # self.close()
        self.cancelConfirm(True)

    def backCancel(self):
        self.readList()
        if any([getattr(config.plugins.vavoomaker, choice).isChanged() for choice in choices]):
            self.session.openWithCallback(self.cancelConfirm, MessageBox, _("Really close without saving settings?"))
        else:
            # self.close()
            self.cancelConfirm(True)

    def deleteBouquets(self):

        def onConfirm(answer):
            if answer:
                self.vavooFetcher.removeAllVavooBouquets()
                self.session.open(MessageBox, _("Reloading Bouquets and Services...\n\nAll Vavoo Favorite Bouquets removed."), MessageBox.TYPE_INFO, timeout=5)
            else:
                self.session.open(MessageBox, _("Operation cancelled."), MessageBox.TYPE_INFO, timeout=5)

        self.session.openWithCallback(
            onConfirm,
            MessageBox,
            _("Remove all Vavoo Favorite Bouquets?"),
            MessageBox.TYPE_YESNO,
            timeout=5,
            default=True
        )

    def cancelConfirm(self, result):
        if not result:
            return
        config.plugins.vavoomaker.current.cancel()
        for ch in choices:
            getattr(config.plugins.vavoomaker, ch).cancel()
        self.close()


class CategorySelector(Screen):
    skin = """
        <screen position="center,center" size="800,650" title="Vavoo Main" flags="wfNoBorder">
            <widget name="list" position="310,70" size="250,150" scrollbarMode="showNever" itemHeight="35" />
            <eLabel name="" position="167,19" size="500,40" backgroundColor="#ff000000" halign="center" valign="center" transparent="1" cornerRadius="26" font="Regular; 28" zPosition="1" text="Select Cowntry for Export" foregroundColor="#fe00" />
            <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/kofi.png" position="40,270" size="250,250" zPosition="5" />
            <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/paypal.png" position="520,270" size="250,250" zPosition="5" />
            <eLabel name="" position="161,528" size="500,40" backgroundColor="#ff000000" halign="center" valign="center" transparent="1" cornerRadius="26" font="Regular; 28" zPosition="1" text="Offer Coffe" foregroundColor="#fe00" />
            <eLabel backgroundColor="#001a2336" position="7,578" size="777,4" zPosition="10" />
            <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="29,595" size="30,30" alphatest="blend" transparent="1" />
            <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="428,595" size="30,30" alphatest="blend" transparent="1" />
            <widget backgroundColor="#9f1313" font="Regular;30" halign="left" position="65,590" size="300,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="1" />
            <widget backgroundColor="#1f771f" font="Regular;30" halign="left" position="465,590" size="300,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="1" />
        </screen>
    """

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.title = _("Select View Type")

        self.list = []
        self["list"] = MenuList(self.list)
        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("OK"))
        self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
            "ok": self.ok,
            "cancel": self.cancel,
            "green": self.ok,
            "red": self.cancel
        }, -1)

        self.list.append((_("View by Countries"), "countries"))
        self.list.append((_("View by Categories"), "categories"))
        self.list.append((_("Plugin Info"), "info"))
        self["list"].setList(self.list)

    def ok(self):
        selection = self["list"].getCurrent()
        if selection:
            view_type = selection[1]
            if view_type == "info":
                self.show_about()
                return
            else:
                self.close(view_type)
        else:
            self.close(None)

    def cancel(self):
        self.close(None)

    def get_plugin_info(self):
        return {
            "name": "Vavoo Maker Playlists",
            "version": __version__,
            "author": __author__,
            "license": __license__,
            "credits": __credits__
        }

    def show_about(self):
        info = self.get_plugin_info()
        about_text = _(
            "Vavoo Maker Playlists v%s\n\n"
            "Author: %s\n"
            "License: %s\n"
            "Credits: %s\n\n"
            "Community: Linuxsat-support.com\n"
            "           Corvoboys.org"
        ) % (info["version"], info["author"], info["license"], ", ".join(info["credits"]))

        self.session.open(MessageBox, about_text, MessageBox.TYPE_INFO)


def PluginMain(session, **kwargs):
    session.openWithCallback(
        lambda view_type: onViewTypeSelected(session, view_type),
        CategorySelector
    )


def onViewTypeSelected(session, view_type):
    if view_type:
        config.plugins.vavoomaker.current.value = view_type
        return session.open(SetupMaker, view_type=view_type)
    else:
        return None


def Plugins(**kwargs):
    return [PluginDescriptor(name="Vavoo Maker v.%s" % __version__, description=_("Make IPTV bouquets based on Vavoo Team"), where=PluginDescriptor.WHERE_PLUGINMENU, icon="icon.png", needsRestart=True, fnc=PluginMain)]
