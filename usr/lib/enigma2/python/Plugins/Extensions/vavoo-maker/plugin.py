#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
#########################################################
#                                                       #
#  Vavoo Maker Playlists Plugin                         #
#  Version: 1.3                                         #
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
__version__ = "1.3"
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
import time
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
from Components.Label import Label
from Components.Sources.StaticText import StaticText
from Components.ConfigList import ConfigListScreen
from Components.config import (
    ConfigSelection,
    getConfigListEntry,
    ConfigSelectionNumber,
    ConfigClock,
    ConfigText,
    configfile,
    config,
    ConfigYesNo,
    ConfigSubsection
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
    trace_error
)

tempDir = "/tmp/vavoo"
if not os_path.exists(tempDir):
    os_makedirs(tempDir)


PLUGIN_PATH = resolveFilename(SCOPE_PLUGINS, "Extensions/{}".format('vavoo-maker'))
PYTHON_VER = version_info.major

_session = None
auto_start_timer = None

# =========================
# Configurazione - usa cfg.
# =========================
config.plugins.vavoomaker = ConfigSubsection()
cfg = config.plugins.vavoomaker

# Scelte per il tipo di visualizzazione
choices = {
    "country": _("Countries"),
    "categories": _("Categories")
}
cfg.current = ConfigSelection(
    choices=[(x[0], x[1]) for x in choices.items()],
    default=list(choices.keys())[0]
)

# Configurazione per ogni tipo
for ch in choices:
    setattr(cfg, ch, ConfigText("", False))

# Configurazione timer aggiornamento automatico
cfg.autobouquetupdate = ConfigYesNo(default=False)
cfg.timetype = ConfigSelection(
    default="interval",
    choices=[("interval", _("interval")), ("fixed time", _("fixed time"))]
)
cfg.updateinterval = ConfigSelectionNumber(default=10, min=5, max=3600, stepwidth=5)
cfg.fixedtime = ConfigClock(default=46800)  # 13:00
cfg.last_update = ConfigText(default="Never")


def get_screen_width():
    """Get current screen width"""
    try:
        from enigma import getDesktop
        desktop = getDesktop(0)
        width = desktop.size().width()
        print("[vUtils] Screen width detected: %d" % width)
        return width
    except Exception as e:
        print("[vUtils] Error getting screen width: %s" % str(e))
        return 1920  # Default FHD


def check_current_config():
    print("=== VAVOO CONFIG STATUS ===")
    print("autobouquetupdate:", cfg.autobouquetupdate.value)
    print("timetype:", cfg.timetype.value)
    print("updateinterval:", cfg.updateinterval.value)
    print("fixedtime:", cfg.fixedtime.value)
    print("last_update:", cfg.last_update.value)
    print("===========================")


check_current_config()


def get_favorite_file():
    """Get the favorite file path in plugin directory"""
    favorite_path = os_path.join(PLUGIN_PATH, 'Favorite.txt')
    # Ensure plugin directory exists and is writable
    if not os_path.exists(PLUGIN_PATH):
        try:
            os_makedirs(PLUGIN_PATH, 0o755)
        except:
            pass

    return favorite_path


def save_bouquets_to_favorite(enabled_bouquets, view_type):
    """Save exported bouquets to Favorite.txt file"""
    favorite_file = get_favorite_file()
    try:
        with open(favorite_file, 'w') as f:
            for bouquet in enabled_bouquets:
                line = "%s|%s|%d\n" % (bouquet, view_type, int(time.time()))
                f.write(line)
        print("[vavoo plugin] Saved %d bouquets to Favorite.txt" % len(enabled_bouquets))
    except Exception as e:
        print("[vavoo plugin] Error saving to Favorite.txt: %s" % str(e))


def load_bouquets_from_favorite():
    """Load saved bouquets from Favorite.txt"""
    favorite_file = get_favorite_file()
    bouquets = []

    try:
        if os_path.exists(favorite_file):
            with open(favorite_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and '|' in line:
                        parts = line.split('|')
                        if len(parts) >= 2:
                            bouquets.append({
                                'name': parts[0],
                                'view_type': parts[1],
                                'timestamp': parts[2] if len(parts) > 2 else '0'
                            })
        print("[vavoo plugin] Loaded %d bouquets from Favorite.txt" % len(bouquets))
    except Exception as e:
        print("[vavoo plugin] Error loading from Favorite.txt: %s" % str(e))

    return bouquets


screen_width = get_screen_width()


class vavoo_maker_config(Screen, ConfigListScreen):
    if screen_width >= 1920:
        if os_path.exists("/usr/bin/apt-get"):
            skin = '''
            <screen name="vavoo_maker_config" position="center,center" size="1920,1080" title="SetupMaker" backgroundColor="transparent" flags="wfNoBorder">
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
                <widget name="version" position="1136,327" size="100,30" zPosition="1" backgroundColor="#30000000" transparent="1" font="Regular; 20" halign="center" foregroundColor="#ffffff" />
                <widget name="statusbar" position="44,649" size="830,40" font="Regular; 24" foregroundColor="yellow" backgroundColor="#101010" transparent="1" zPosition="3" />
                <eLabel name="" position="22,30" size="1244,690" zPosition="-90" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                <eLabel backgroundColor="#001a2336" position="34,90" size="1220,3" zPosition="10" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="619,386" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="619,434" size="30,30" alphatest="blend" transparent="1" />
                <widget backgroundColor="#9f1313" font="Regular;30" halign="left" position="660,380" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="3" />
                <widget backgroundColor="#1f771f" font="Regular;30" halign="left" position="660,430" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="3" />
                <widget name="config" position="40,100" size="550,524" itemHeight="35" enableWrapAround="1" transparent="0" zPosition="9" scrollbarMode="showOnDemand" />
                <widget name="description" position="621,599" size="635,81" font="Regular; 32" halign="center" foregroundColor="#00ffffff" transparent="1" zPosition="3" />
                <eLabel backgroundColor="#00fffffe" position="35,695" size="1200,3" zPosition="10" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/log.png" position="616,109" size="512,256" zPosition="5" />
                <widget source="session.CurrentService" render="Label" position="915,561" size="350,34" font="Regular;26" borderWidth="1" backgroundColor="background" transparent="1" halign="center" foregroundColor="white" zPosition="30" valign="center" noWrap="1">
                    <convert type="ServiceName">Name</convert>
                </widget>
                <widget source="session.VideoPicture" render="Pig" position="936,375" zPosition="20" size="300,180" backgroundColor="transparent" transparent="0" cornerRadius="14" />
            </screen>'''

        else:
            skin = '''
                <screen name="vavoo_maker_config" position="center,center" size="1920,1080" title="Setup Vavoo Maker" backgroundColor="transparent" flags="wfNoBorder" zPosition="-10">
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
                    <widget name="version" position="973,180" size="100,30" zPosition="9" backgroundColor="#30000000" transparent="1" font="Regular; 20" halign="center" foregroundColor="#ffffff" />
                    <widget name="statusbar" position="44,644" size="830,40" font="Regular; 24" foregroundColor="yellow" backgroundColor="#101010" transparent="1" zPosition="3" />
                    <eLabel name="" position="22,30" size="1244,690" zPosition="-90" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                    <eLabel backgroundColor="#001a2336" position="34,90" size="1220,3" zPosition="10" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="643,466" size="30,30" alphatest="blend" transparent="1" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="644,512" size="30,30" alphatest="blend" transparent="1" />
                    <widget backgroundColor="#9f1313" font="Regular;30" halign="left" position="676,461" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="3" />
                    <widget backgroundColor="#1f771f" font="Regular;30" halign="left" position="676,506" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="3" />
                    <widget name="config" position="30,100" size="606,524" itemHeight="32" font="Regular;34" enableWrapAround="1" transparent="0" zPosition="9" scrollbarMode="showOnDemand" />
                    <widget name="description" position="621,599" size="635,81" font="Regular; 32" halign="center" foregroundColor="#00ffffff" transparent="1" zPosition="3" />
                    <eLabel backgroundColor="#00fffffe" position="35,695" size="1200,3" zPosition="10" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/log.png" position="732,100" size="512,256" zPosition="5" />
                    <widget source="session.CurrentService" render="Label" position="915,561" size="350,34" font="Regular;26" borderWidth="1" backgroundColor="background" transparent="1" halign="center" foregroundColor="white" zPosition="30" valign="center" noWrap="1">
                        <convert type="ServiceName">Name</convert>
                    </widget>
                    <widget source="session.VideoPicture" render="Pig" position="936,375" zPosition="20" size="300,180" backgroundColor="transparent" transparent="0" cornerRadius="14" />
                </screen>'''
    else:
        if os_path.exists("/usr/bin/apt-get"):
            skin = '''
                <screen name="vavoo_maker_config" position="center,center" size="1280,720" title="Setup Vavoo Maker" backgroundColor="transparent" flags="wfNoBorder" zPosition="-10">
                    <eLabel backgroundColor="#002d3d5b" cornerRadius="20" position="0,0" size="1280,720" zPosition="-99" />
                    <eLabel name="" position="11,10" size="1260,700" zPosition="-90" cornerRadius="18" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                    <!-- /* time -->
                    <eLabel name="" position="30,24" size="700,52" backgroundColor="#00171a1c" halign="center" valign="center" transparent="0" font="Regular; 36" zPosition="1" text="VAVOO MAKER BY LULULLA" foregroundColor="#007fcfff" />
                    <widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="1107,40" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="120,40" source="global.CurrentTime" transparent="1" zPosition="3">
                        <convert type="ClockToText">Default</convert>
                    </widget>
                    <widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="731,38" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="400,40" source="global.CurrentTime" transparent="1" zPosition="3">
                        <convert type="ClockToText">Date</convert>
                    </widget>
                    <widget name="version" position="1075,157" size="100,30" zPosition="9" backgroundColor="#30000000" transparent="1" font="Regular; 20" halign="center" foregroundColor="#ffffff" />
                    <widget name="statusbar" position="34,644" size="830,40" font="Regular; 24" foregroundColor="yellow" backgroundColor="#101010" transparent="1" zPosition="3" />
                    <eLabel name="" position="22,20" size="1244,670" zPosition="-90" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                    <eLabel backgroundColor="#001a2336" position="34,90" size="1220,3" zPosition="10" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="643,466" size="30,30" alphatest="blend" transparent="1" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="644,512" size="30,30" alphatest="blend" transparent="1" />
                    <widget backgroundColor="#9f1313" font="Regular; 26" halign="left" position="676,461" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="3" />
                    <widget backgroundColor="#1f771f" font="Regular; 26" halign="left" position="676,506" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="3" />
                    <widget name="config" position="30,100" size="606,524" itemHeight="32" enableWrapAround="1" transparent="0" zPosition="9" scrollbarMode="showOnDemand" />
                    <widget name="description" position="621,599" size="635,81" font="Regular; 28" halign="center" foregroundColor="#00ffffff" transparent="1" zPosition="3" />
                    <eLabel backgroundColor="#00fffffe" position="35,695" size="1200,3" zPosition="10" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/log.png" position="732,100" size="512,256" zPosition="5" />
                    <widget source="session.CurrentService" render="Label" position="915,561" size="350,34" font="Regular;26" borderWidth="1" backgroundColor="background" transparent="1" halign="center" foregroundColor="white" zPosition="30" valign="center" noWrap="1">
                        <convert type="ServiceName">Name</convert>
                    </widget>
                    <widget source="session.VideoPicture" render="Pig" position="936,375" zPosition="20" size="300,180" backgroundColor="transparent" transparent="0" cornerRadius="14" />
                </screen>'''
        else:
            skin = '''
                <screen name="vavoo_maker_config" position="center,center" size="1280,720" title="Setup Vavoo Maker" backgroundColor="transparent" flags="wfNoBorder" zPosition="-10">
                    <eLabel backgroundColor="#002d3d5b" cornerRadius="20" position="0,0" size="1280,720" zPosition="-99" />
                    <eLabel name="" position="11,10" size="1260,700" zPosition="-90" cornerRadius="18" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                    <!-- /* time -->
                    <eLabel name="" position="30,24" size="700,52" backgroundColor="#00171a1c" halign="center" valign="center" transparent="0" font="Regular; 36" zPosition="1" text="VAVOO MAKER BY LULULLA" foregroundColor="#007fcfff" />
                    <widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="1107,40" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="120,40" source="global.CurrentTime" transparent="1" zPosition="3">
                        <convert type="ClockToText">Default</convert>
                    </widget>
                    <widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="731,38" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="400,40" source="global.CurrentTime" transparent="1" zPosition="3">
                        <convert type="ClockToText">Date</convert>
                    </widget>
                    <widget name="version" position="1075,157" size="100,30" zPosition="9" backgroundColor="#30000000" transparent="1" font="Regular; 20" halign="center" foregroundColor="#ffffff" />
                    <widget name="statusbar" position="34,644" size="830,40" font="Regular; 24" foregroundColor="yellow" backgroundColor="#101010" transparent="1" zPosition="3" />
                    <eLabel name="" position="22,20" size="1244,670" zPosition="-90" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                    <eLabel backgroundColor="#001a2336" position="34,90" size="1220,3" zPosition="10" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="643,466" size="30,30" alphatest="blend" transparent="1" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="644,512" size="30,30" alphatest="blend" transparent="1" />
                    <widget backgroundColor="#9f1313" font="Regular; 26" halign="left" position="676,461" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="3" />
                    <widget backgroundColor="#1f771f" font="Regular; 26" halign="left" position="676,506" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="3" />
                    <widget name="config" position="30,100" size="606,524" itemHeight="32" font="Regular;34" enableWrapAround="1" transparent="0" zPosition="9" scrollbarMode="showOnDemand" />
                    <widget name="description" position="621,599" size="635,81" font="Regular; 28" halign="center" foregroundColor="#00ffffff" transparent="1" zPosition="3" />
                    <eLabel backgroundColor="#00fffffe" position="35,695" size="1200,3" zPosition="10" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/log.png" position="732,100" size="512,256" zPosition="5" />
                    <widget source="session.CurrentService" render="Label" position="915,561" size="350,34" font="Regular;26" borderWidth="1" backgroundColor="background" transparent="1" halign="center" foregroundColor="white" zPosition="30" valign="center" noWrap="1">
                        <convert type="ServiceName">Name</convert>
                    </widget>
                    <widget source="session.VideoPicture" render="Pig" position="936,375" zPosition="20" size="300,180" backgroundColor="transparent" transparent="0" cornerRadius="14" />
                </screen>'''

    def __init__(self, session):
        Screen.__init__(self, session)
        self.session = session
        self.setup_title = ('Vavoo Maker Config')
        self.list = []
        self.onChangedEntry = []
        self["version"] = Label()
        self['statusbar'] = Label()
        self["description"] = Label("")
        self["red"] = Label(_("Back"))
        self["green"] = Label(_("Save"))
        self['actions'] = ActionMap(['OkCancelActions', 'ColorActions', 'DirectionActions'], {
            "cancel": self.extnok,
            "left": self.keyLeft,
            "right": self.keyRight,
            "up": self.keyUp,
            "down": self.keyDown,
            "red": self.extnok,
            "green": self.save,
            "ok": self.keyOK,
        }, -1)
        self.update_status()
        ConfigListScreen.__init__(
            self,
            self.list,
            session=self.session,
            on_change=self.changedEntry)
        self.createSetup()
        self.showhide()
        self.onLayoutFinish.append(self.layoutFinished)

    def layoutFinished(self):
        self.setTitle(self.setup_title)
        self['version'].setText('V.' + __version__)

    def keyOK(self):
        pass

    def update_status(self):
        if cfg.autobouquetupdate:
            self['statusbar'].setText(
                _("Last channel update: %s") %
                cfg.last_update.value)

    def createSetup(self):
        self.list = []
        indent = "- "
        self.list.append(
            getConfigListEntry(
                _("Scheduled Bouquet Update:"),
                cfg.autobouquetupdate,  # USA cfg.
                _("Active Automatic Bouquet Update")))

        if cfg.autobouquetupdate.value is True:  # USA cfg.
            self.list.append(
                getConfigListEntry(
                    indent + _("Schedule type:"),
                    cfg.timetype,  # USA cfg.
                    _("At an interval of hours or at a fixed time")))
            if cfg.timetype.value == "interval":  # USA cfg.
                self.list.append(
                    getConfigListEntry(
                        2 * indent + _("Update interval (minutes):"),
                        cfg.updateinterval,  # USA cfg.
                        _("Configure every interval of minutes from now")))
            if cfg.timetype.value == "fixed time":  # USA cfg.
                self.list.append(
                    getConfigListEntry(
                        2 * indent + _("Time to start update:"),
                        cfg.fixedtime,  # USA cfg.
                        _("Configure at a fixed time")))

        self["config"].list = self.list
        self["config"].l.setList(self.list)
        self.setInfo()

    def setInfo(self):
        try:
            sel = self['config'].getCurrent()[2]
            if sel:
                self['description'].setText(str(sel))
            else:
                self['description'].setText(_('SELECT YOUR CHOICE'))
            return
        except Exception as error:
            print('error as:', error)
            trace_error()

    def changedEntry(self):
        self.item = self["config"].getCurrent()
        for x in self.onChangedEntry:
            x()
        # self['green'].instance.setText(
            # _('Save') if self['config'].isChanged() else '- - - -')

    def getCurrentEntry(self):
        return self["config"].getCurrent()[0]

    def showhide(self):
        pass

    def getCurrentValue(self):
        return str(self["config"].getCurrent()[1].getText())

    def createSummary(self):
        from Screens.Setup import SetupSummary
        return SetupSummary

    def keyLeft(self):
        ConfigListScreen.keyLeft(self)
        # sel = self["config"].getCurrent()[1]  # Keep for future debug
        self.createSetup()
        self.showhide()

    def keyRight(self):
        ConfigListScreen.keyRight(self)
        # sel = self["config"].getCurrent()[1]  # Keep for future debug
        self.createSetup()
        self.showhide()

    def keyDown(self):
        self['config'].instance.moveSelection(self['config'].instance.moveDown)
        self.createSetup()
        self.showhide()

    def keyUp(self):
        self['config'].instance.moveSelection(self['config'].instance.moveUp)
        self.createSetup()
        self.showhide()

    def save(self):
        if self["config"].isChanged():
            for x in self["config"].list:
                x[1].save()

            configfile.save()

            try:
                config.loadFromFile(configfile.CONFIG_FILE)
            except:
                pass

            # RESTART timer
            global auto_start_timer
            if auto_start_timer is not None:
                auto_start_timer.update()
            else:
                auto_start_timer = AutoStartTimer(self.session)

            self.session.open(
                MessageBox,
                _("Configuration saved successfully!"),
                MessageBox.TYPE_INFO,
                timeout=5
            )

            self.close()

    def _safe_config_reload(self):
        """Safe configuration reload"""
        try:
            if not hasattr(config.plugins, 'vavoomaker'):
                config.plugins.vavoomaker = ConfigSubsection()
                print("Recreated vavoo config section")

            config.loadFromFile(configfile.CONFIG_FILE)
        except Exception as e:
            print("Safe config reload failed: " + str(e))

    def extnok(self, answer=None):
        if answer is None:
            if self['config'].isChanged():
                self.session.openWithCallback(
                    self.extnok, MessageBox, _("Really close without saving settings?"))
            else:
                self.close()
        elif answer:
            for x in self["config"].list:
                x[1].cancel()
            self.close()
        else:
            return


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
                if mtime < time.time() - 86400:  # if file is older than one day delete it
                    os_remove(self.cachefile)
                else:
                    with open(self.cachefile, 'rb') as cache_input:
                        if PYTHON_VER == 3:
                            self.playlists_processed = pickle.load(cache_input, encoding='bytes')
                        else:
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
    if screen_width >= 1920:

        if os_path.exists("/usr/bin/apt-get"):
            skin = '''
                <screen name="SetupMaker" position="center,center" size="1920,1080" title="SetupMaker" backgroundColor="transparent" flags="wfNoBorder">
                    <eLabel backgroundColor="#002d3d5b" cornerRadius="20" position="19,22" size="1255,711" zPosition="-99" />
                    <eLabel name="" position="26,30" size="1240,697" zPosition="-90" cornerRadius="18" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                    <!-- /* time -->
                    <eLabel name="" position="30,34" size="700,52" backgroundColor="#00171a1c" halign="center" valign="center" transparent="0" font="Regular; 36" zPosition="1" text="VAVOO MAKER BY LULULLA" foregroundColor="#007fcfff" />
                    <widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="1107,40" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="120,40" source="global.CurrentTime" transparent="1" zPosition="3">
                        <convert type="ClockToText">Default</convert>
                    </widget>
                    <widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="731,41" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="400,40" source="global.CurrentTime" transparent="1" zPosition="3">
                        <convert type="ClockToText">Date</convert>
                    </widget>
                    <eLabel name="" position="33,36" size="1230,663" zPosition="-90" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                    <eLabel backgroundColor="#001a2336" position="34,90" size="1220,3" zPosition="10" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="619,386" size="30,30" alphatest="blend" transparent="1" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="619,434" size="30,30" alphatest="blend" transparent="1" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_yellow.png" position="620,486" size="30,30" alphatest="blend" transparent="1" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_blue.png" position="620,534" size="30,30" alphatest="blend" transparent="1" />
                    <widget backgroundColor="#9f1313" font="Regular;30" halign="left" position="660,380" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="3" />
                    <widget backgroundColor="#1f771f" font="Regular;30" halign="left" position="660,430" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="3" />
                    <widget backgroundColor="#a08500" font="Regular;30" halign="left" position="660,480" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_yellow" transparent="1" valign="center" zPosition="3" />
                    <widget backgroundColor="#18188b" font="Regular;30" halign="left" position="661,530" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_blue" transparent="1" valign="center" zPosition="3" />
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
                    <eLabel name="" position="26,30" size="1240,697" zPosition="-90" cornerRadius="18" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                    <!-- /* time -->
                    <eLabel name="" position="30,34" size="700,52" backgroundColor="#00171a1c" halign="center" valign="center" transparent="0" font="Regular; 36" zPosition="1" text="VAVOO MAKER BY LULULLA" foregroundColor="#007fcfff" />
                    <widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="1107,40" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="120,40" source="global.CurrentTime" transparent="1" zPosition="3">
                        <convert type="ClockToText">Default</convert>
                    </widget>
                    <widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="731,41" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="400,40" source="global.CurrentTime" transparent="1" zPosition="3">
                        <convert type="ClockToText">Date</convert>
                    </widget>
                    <eLabel name="" position="33,36" size="1230,663" zPosition="-90" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                    <eLabel backgroundColor="#001a2336" position="34,90" size="1220,3" zPosition="10" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="619,386" size="30,30" alphatest="blend" transparent="1" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="619,434" size="30,30" alphatest="blend" transparent="1" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_yellow.png" position="620,486" size="30,30" alphatest="blend" transparent="1" />
                    <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_blue.png" position="620,534" size="30,30" alphatest="blend" transparent="1" />
                    <widget backgroundColor="#9f1313" font="Regular;30" halign="left" position="660,380" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="3" />
                    <widget backgroundColor="#1f771f" font="Regular;30" halign="left" position="660,430" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="3" />
                    <widget backgroundColor="#a08500" font="Regular;30" halign="left" position="660,480" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_yellow" transparent="1" valign="center" zPosition="3" />
                    <widget backgroundColor="#18188b" font="Regular;30" halign="left" position="661,530" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_blue" transparent="1" valign="center" zPosition="3" />
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
    else:
        if os_path.exists("/usr/bin/apt-get"):
            skin = '''
            <screen name="SetupMaker" position="center,center" size="1280,720" title="SetupMaker" backgroundColor="transparent" flags="wfNoBorder">
                <eLabel backgroundColor="#002d3d5b" cornerRadius="20" position="0,0" size="1280,720" zPosition="-99" />
                <eLabel name="" position="10,10" size="1263,701" zPosition="-90" cornerRadius="18" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                <!-- /* time -->
                <eLabel name="" position="30,34" size="700,52" backgroundColor="#00171a1c" halign="center" valign="center" transparent="0" font="Regular; 36" zPosition="1" text="VAVOO MAKER BY LULULLA" foregroundColor="#007fcfff" />
                <widget backgroundColor="#00171a1c" font="Regular; 30" halign="right" position="1107,35" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="120,40" source="global.CurrentTime" transparent="1" zPosition="3">
                    <convert type="ClockToText">Default</convert>
                </widget>
                <widget backgroundColor="#00171a1c" font="Regular; 30" halign="right" position="736,35" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="400,40" source="global.CurrentTime" transparent="1" zPosition="3">
                    <convert type="ClockToText">Date</convert>
                </widget>
                <eLabel name="" position="20,16" size="1245,689" zPosition="-90" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                <eLabel backgroundColor="#001a2336" position="34,90" size="1220,3" zPosition="10" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="619,386" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="619,434" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_yellow.png" position="620,486" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_blue.png" position="620,534" size="30,30" alphatest="blend" transparent="1" />
                <widget backgroundColor="#9f1313" font="Regular; 24" halign="left" position="660,380" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="3" />
                <widget backgroundColor="#1f771f" font="Regular; 24" halign="left" position="660,430" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="3" />
                <widget backgroundColor="#a08500" font="Regular; 24" halign="left" position="660,480" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_yellow" transparent="1" valign="center" zPosition="3" />
                <widget backgroundColor="#18188b" font="Regular; 24" halign="left" position="661,530" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_blue" transparent="1" valign="center" zPosition="3" />
                <widget name="config" position="40,100" size="550,585" itemHeight="35" enableWrapAround="1" transparent="0" zPosition="9" scrollbarMode="showOnDemand" />
                <widget name="description" position="610,604" size="635,81" font="Regular; 26" halign="center" foregroundColor="#00ffffff" transparent="1" zPosition="3" />
                <eLabel backgroundColor="#00fffffe" position="35,695" size="1200,3" zPosition="10" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/log.png" position="616,109" size="512,256" zPosition="5" />
                <widget source="session.CurrentService" render="Label" position="915,561" size="350,34" font="Regular; 20" borderWidth="1" backgroundColor="background" transparent="1" halign="center" foregroundColor="white" zPosition="30" valign="center" noWrap="1">
                    <convert type="ServiceName">Name</convert>
                </widget>
                <widget source="session.VideoPicture" render="Pig" position="936,375" zPosition="20" size="300,180" backgroundColor="transparent" transparent="0" cornerRadius="14" />
            </screen>'''
        else:
            skin = '''
            <screen name="SetupMaker" position="center,center" size="1280,720" title="SetupMaker" backgroundColor="transparent" flags="wfNoBorder">
                <eLabel backgroundColor="#002d3d5b" cornerRadius="20" position="0,0" size="1280,720" zPosition="-99" />
                <eLabel name="" position="10,10" size="1263,701" zPosition="-90" cornerRadius="18" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                <!-- /* time -->
                <eLabel name="" position="30,34" size="700,52" backgroundColor="#00171a1c" halign="center" valign="center" transparent="0" font="Regular; 36" zPosition="1" text="VAVOO MAKER BY LULULLA" foregroundColor="#007fcfff" />
                <widget backgroundColor="#00171a1c" font="Regular; 30" halign="right" position="1107,35" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="120,40" source="global.CurrentTime" transparent="1" zPosition="3">
                    <convert type="ClockToText">Default</convert>
                </widget>
                <widget backgroundColor="#00171a1c" font="Regular; 30" halign="right" position="736,35" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="400,40" source="global.CurrentTime" transparent="1" zPosition="3">
                    <convert type="ClockToText">Date</convert>
                </widget>
                <eLabel name="" position="20,16" size="1245,689" zPosition="-90" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
                <eLabel backgroundColor="#001a2336" position="34,90" size="1220,3" zPosition="10" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="619,386" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="619,434" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_yellow.png" position="620,486" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_blue.png" position="620,534" size="30,30" alphatest="blend" transparent="1" />
                <widget backgroundColor="#9f1313" font="Regular; 24" halign="left" position="660,380" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="3" />
                <widget backgroundColor="#1f771f" font="Regular; 24" halign="left" position="660,430" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="3" />
                <widget backgroundColor="#a08500" font="Regular; 24" halign="left" position="660,480" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_yellow" transparent="1" valign="center" zPosition="3" />
                <widget backgroundColor="#18188b" font="Regular; 24" halign="left" position="661,530" size="250,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_blue" transparent="1" valign="center" zPosition="3" />
                <widget name="config" position="40,100" size="550,585" itemHeight="35" font="Regular; 30" enableWrapAround="1" transparent="0" zPosition="9" scrollbarMode="showOnDemand" />
                <widget name="description" position="610,604" size="635,81" font="Regular; 26" halign="center" foregroundColor="#00ffffff" transparent="1" zPosition="3" />
                <eLabel backgroundColor="#00fffffe" position="35,695" size="1200,3" zPosition="10" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/log.png" position="616,109" size="512,256" zPosition="5" />
                <widget source="session.CurrentService" render="Label" position="915,561" size="350,34" font="Regular; 20" borderWidth="1" backgroundColor="background" transparent="1" halign="center" foregroundColor="white" zPosition="30" valign="center" noWrap="1">
                    <convert type="ServiceName">Name</convert>
                </widget>
                <widget source="session.VideoPicture" render="Pig" position="936,375" zPosition="20" size="300,180" backgroundColor="transparent" transparent="0" cornerRadius="14" />
            </screen>'''

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
        # Create bouquets
        self.vavooFetcher.createBouquet(self.enabled)

        # DEBUG: Check what we're saving
        print("[DEBUG] Saving bouquets to favorite:")
        print("[DEBUG] Enabled bouquets:", self.enabled)
        print("[DEBUG] View type:", self.view_type)

        save_bouquets_to_favorite(self.enabled, self.view_type)

        # Close the screen
        self.cancelConfirm(True)

    def backCancel(self):
        self.readList()
        if any([getattr(config.plugins.vavoomaker, choice).isChanged() for choice in choices]):
            self.session.openWithCallback(self.cancelConfirm, MessageBox, _("Really close without saving settings?"))
        else:
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
    if screen_width >= 1920:
        skin = """
            <screen position="center,center" size="1280,720" title="Vavoo Main" flags="wfNoBorder">
                <widget name="list" position="310,70" size="250,150" scrollbarMode="showNever" itemHeight="35" />
                <eLabel name="" position="167,19" size="500,40" backgroundColor="#ff000000" halign="center" valign="center" transparent="1" cornerRadius="26" font="Regular; 28" zPosition="1" text="Select Cowntry for Export" foregroundColor="#fe00" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/kofi.png" position="74,263" size="250,250" zPosition="5" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/paypal.png" position="463,262" size="250,250" zPosition="5" />
                <eLabel name="" position="161,528" size="500,40" backgroundColor="#ff000000" halign="center" valign="center" transparent="1" cornerRadius="26" font="Regular; 28" zPosition="1" text="Offer Coffe" foregroundColor="#fe00" />
                <eLabel backgroundColor="#001a2336" position="22,577" size="718,5" zPosition="10" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="29,595" size="30,30" alphatest="blend" transparent="1" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="403,595" size="30,30" alphatest="blend" transparent="1" />
                <widget backgroundColor="#9f1313" font="Regular;30" halign="left" position="65,590" size="300,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="3" />
                <widget backgroundColor="#1f771f" font="Regular;30" halign="left" position="440,590" size="300,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="3" />
                <widget source="session.VideoPicture" render="Pig" position="733,62" zPosition="19" size="520,308" backgroundColor="transparent" transparent="0" cornerRadius="14" />
                <ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/log.png" position="742,397" size="512,256" zPosition="5" />
            </screen>"""
    else:
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
                <widget backgroundColor="#9f1313" font="Regular;30" halign="left" position="65,590" size="300,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="3" />
                <widget backgroundColor="#1f771f" font="Regular;30" halign="left" position="465,590" size="300,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="3" />
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
        self.list.append((_("Setup"), "setup"))
        self.list.append((_("Plugin Info"), "info"))
        self["list"].setList(self.list)

    def ok(self):
        selection = self["list"].getCurrent()
        if selection:
            view_type = selection[1]
            if view_type == "info":
                self.show_about()
                return
            elif view_type == "setup":
                self.go_vavoo_maker_config()
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

    def go_vavoo_maker_config(self):
        self.session.open(vavoo_maker_config)

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
    """Manages selection from the main menu"""
    if view_type in ["countries", "categories"]:
        cfg.current.value = view_type
        return session.open(SetupMaker, view_type=view_type)
    elif view_type == "setup":
        return None
    elif view_type == "info":
        return None
    else:
        return None


class AutoStartTimer:
    def __init__(self, session):
        print("*** AutoStartTimer INIT ***")
        print("*** AutoUpdate enabled:", cfg.autobouquetupdate.value)
        print("*** Timer type:", cfg.timetype.value)
        print("*** Update interval:", cfg.updateinterval.value)

        self.session = session
        self.timer = eTimer()
        try:
            self.timer.callback.append(self.on_timer)
        except BaseException:
            self.timer_conn = self.timer.timeout.connect(self.on_timer)
        self.timer.start(100, True)
        self.update()

    def update(self, constant=0):
        self.timer.stop()
        wake = self.get_wake_time()
        nowt = time.time()

        print("*** Next wake time:", wake)
        print("*** Current time:", nowt)
        print("*** Wake in seconds:", wake - nowt if wake > 0 else "DISABLED")

        if wake > 0:
            if wake < nowt + constant:
                if cfg.timetype.value == "interval":
                    interval = int(cfg.updateinterval.value)
                    wake += interval * 60
                elif cfg.timetype.value == "fixed time":
                    wake += 86400
            next_time = wake - int(nowt)
            if next_time > 3600:
                next_time = 3600
            if next_time <= 0:
                next_time = 60

            print("*** Timer set for:", next_time, "seconds")
            self.timer.startLongTimer(next_time)
        else:
            wake = -1
            print("*** Timer DISABLED")
        return wake

    def get_wake_time(self):
        if cfg.autobouquetupdate.value is True:
            if cfg.timetype.value == "interval":
                interval = int(cfg.updateinterval.value)
                nowt = time.time()
                return int(nowt) + interval * 60
            if cfg.timetype.value == "fixed time":
                ftc = cfg.fixedtime.value
                now = time.localtime(time.time())
                fwt = int(time.mktime((
                    now.tm_year,
                    now.tm_mon,
                    now.tm_mday,
                    ftc[0],
                    ftc[1],
                    now.tm_sec,
                    now.tm_wday,
                    now.tm_yday,
                    now.tm_isdst
                )))
                return fwt
        else:
            return -1

    def on_timer(self):
        self.timer.stop()
        now = int(time.time())
        wake = now
        constant = 0
        if cfg.timetype.value == "fixed time":
            wake = self.get_wake_time()
        if abs(wake - now) < 60:
            try:
                self.startMain()
                constant = 60
                localtime = time.asctime(time.localtime(time.time()))
                cfg.last_update.value = localtime
                cfg.last_update.save()
            except Exception as error:
                print("Error in AutoStartTimer:", error)
        self.update(constant)

    def startMain(self):
        """Update all bouquets saved in Favorite.txt"""
        if self.session is None:
            print("AutoStartTimer: No session available, running in background")

        favorite_file = get_favorite_file()

        if not os_path.exists(favorite_file):
            print("Favorite.txt not found - no bouquets to update")
            return

        try:
            bouquets_to_update = load_bouquets_from_favorite()

            if not bouquets_to_update:
                print("No bouquets found in Favorite.txt")
                return

            print("Scheduled update for " + str(len(bouquets_to_update)) + " bouquets")

            for bouquet_info in bouquets_to_update:
                bouquet_name = bouquet_info['name']
                view_type = bouquet_info['view_type']

                print("Updating bouquet: " + bouquet_name + " (type: " + view_type + ")")

                cfg.current.value = view_type

                fetcher = vavooFetcher()
                fetcher.getPlaylist()

                enabled_list = [bouquet_name]
                fetcher.createBouquet(enabled_list)

                print("Successfully updated: " + bouquet_name)

            localtime = time.asctime(time.localtime(time.time()))
            cfg.last_update.value = localtime
            cfg.last_update.save()

            print("All bouquets updated successfully")

            if self.session is not None:
                self.session.open(
                    MessageBox,
                    _("Bouquets updated successfully!"),
                    MessageBox.TYPE_INFO,
                    timeout=5
                )

        except Exception as e:
            print("Error during scheduled update:", e)
            if self.session is not None:
                self.session.open(
                    MessageBox,
                    _("Error during bouquet update: %s") % str(e),
                    MessageBox.TYPE_ERROR,
                    timeout=5
                )


def autostart(reason, session=None, **kwargs):
    global auto_start_timer
    global _session

    if reason == 0 and _session is None:
        if session is not None:
            _session = session
            if auto_start_timer is None:
                auto_start_timer = AutoStartTimer(session)

    elif reason == 1:
        if session is not None and _session is None:
            _session = session
            if auto_start_timer is None:
                auto_start_timer = AutoStartTimer(session)

    return


def get_next_wakeup():
    """Returns the next wakeup for the timer"""
    if cfg.autobouquetupdate.value:
        auto_timer = AutoStartTimer(None)
        return auto_timer.get_wake_time()
    return -1


def cfgmain(menuid, **kwargs):
    """Adds entry to main menu"""
    if menuid == "mainmenu":
        return [(_('Vavoo Maker'), PluginMain, 'VavooMaker', 11)]
    else:
        return []


def Plugins(**kwargs):
    plugin_description = _("Create IPTV bouquets based on Vavoo Team")
    plugin_icon = "icon.png"

    result = []

    # Main menu
    main_descriptor = PluginDescriptor(
        name="Vavoo Maker v.%s" % __version__,
        description=plugin_description,
        where=PluginDescriptor.WHERE_MENU,
        icon=plugin_icon,
        fnc=cfgmain
    )

    # Plugin menu
    plugin_menu_descriptor = PluginDescriptor(
        name="Vavoo Maker v.%s" % __version__,
        description=plugin_description,
        where=PluginDescriptor.WHERE_PLUGINMENU,
        icon=plugin_icon,
        fnc=PluginMain,
        needsRestart=True,
    )

    # Autostart
    autostart_descriptor = PluginDescriptor(
        name="Vavoo Maker v.%s" % __version__,
        description=plugin_description,
        where=[
            PluginDescriptor.WHERE_AUTOSTART,
            PluginDescriptor.WHERE_SESSIONSTART
        ],
        fnc=autostart,
        wakeupfnc=get_next_wakeup
    )

    result.extend([main_descriptor, plugin_menu_descriptor, autostart_descriptor])
    return result
