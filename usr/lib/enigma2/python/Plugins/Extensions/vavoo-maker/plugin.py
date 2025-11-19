#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
# ***************************************
#        coded by Lululla               *
#  Start and update  11/02/2025         *
#    Thank's Warder for test :)         *
# ***************************************
# ATTENTION PLEASE...
# This is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2, or (at your option) any later
# version.
# You must not remove the credits at
# all and you must make the modified
# code open to everyone. by Lululla
# ========================================
# Info :
# Linuxsat-support.com & corvoboys.org
"""

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
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.config import config, ConfigSubsection, ConfigSelection, ConfigText, configfile
from Plugins.Plugin import PluginDescriptor
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.Directories import (SCOPE_PLUGINS, resolveFilename)
from enigma import eTimer
from os import (
	listdir as os_listdir,
	makedirs as os_makedirs,
	path as os_path,
	remove as os_remove,
)
from requests import get, exceptions
from shutil import rmtree
# from re import DOTALL  # , compile
from time import time
import json
import codecs
from sys import version_info

if os_path.exists("/usr/bin/apt-get"):
	from .SelDMList import SelectionList, SelectionEntryComponent
	base_class = Screen
else:
	from .SelList import SelectionList, SelectionEntryComponent
	from Screens.Screen import Screen, ScreenSummary
	base_class = ScreenSummary


tempDir = "/tmp/vavoo"
if not os_path.exists(tempDir):
	os_makedirs(tempDir)

PLUGIN_PATH = resolveFilename(SCOPE_PLUGINS, "Extensions/{}".format('vavoo-maker'))
config.plugins.vavoomaker = ConfigSubsection()
choices = {"country": _("country")}
config.plugins.vavoomaker.current = ConfigSelection(choices=[(x[0], x[1]) for x in choices.items()], default=list(choices.keys())[0])
for ch in choices:
	setattr(config.plugins.vavoomaker, ch, ConfigText("", False))


PYTHON_VER = version_info.major


class vavooFetcher():
	def __init__(self):

		self.tempDir = "/tmp/vavoo"
		if not os_path.exists(self.tempDir):
			os_makedirs(self.tempDir)

		self.cachefile = os_path.join(self.tempDir, "vavoo.cache")
		self.playlists = {"country": "https://vavoo.to/channels"}
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
			<screen name="SetupMaker" position="center,center" size="1920,1080" title="SetupMaker" backgroundColor="#050c101b" flags="wfNoBorder">
				<eLabel backgroundColor="#002d3d5b" cornerRadius="20" position="0,0" size="1920,1080" zPosition="-99" />
				<eLabel backgroundColor="#001a2336" cornerRadius="30" position="20,1014" size="1880,60" zPosition="-80" />
				<eLabel name="" position="31,30" size="1220,977" zPosition="-90" cornerRadius="18" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />

				<!-- /* time -->
				<eLabel name="" position="38,38" size="1207,52" backgroundColor="#00171a1c" halign="center" valign="center" transparent="0" font="Regular; 36" zPosition="1" text="VAVOO MAKER BY LULULLA" foregroundColor="#007fcfff" />

				<widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="1775,25" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="120,40" source="global.CurrentTime" transparent="1">
					<convert type="ClockToText">Default</convert>
				</widget>
				<widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="1385,25" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="400,40" source="global.CurrentTime" transparent="1">
					<convert type="ClockToText">Date</convert>
				</widget>

				<widget source="session.VideoPicture" render="Pig" position="1280,120" zPosition="20" size="622,350" backgroundColor="#ff000000" transparent="0" />

				<eLabel name="" position="20,30" size="1244,977" zPosition="-90" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
				<eLabel backgroundColor="#002d3d5b" position="0,0" size="1920,1080" zPosition="-1" />
				<eLabel backgroundColor="#001a2336" position="20,1014" size="1880,60" zPosition="-80" />

				<eLabel backgroundColor="#001a2336" position="34,90" size="1220,3" zPosition="10" />
				<ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="32,1029" size="30,30" alphatest="blend" transparent="1" />
				<ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="342,1034" size="30,30" alphatest="blend" transparent="1" />
				<ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_yellow.png" position="652,1034" size="30,30" alphatest="blend" transparent="1" />
				<ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_blue.png" position="962,1034" size="30,30" alphatest="blend" transparent="1" />

				<widget backgroundColor="#9f1313" font="Regular;30" halign="left" position="65,1025" size="300,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="1" />
				<widget backgroundColor="#1f771f" font="Regular;30" halign="left" position="380,1025" size="300,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="1" />
				<widget backgroundColor="#a08500" font="Regular;30" halign="left" position="685,1025" size="300,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_yellow" transparent="1" valign="center" zPosition="1" />
				<widget backgroundColor="#18188b" font="Regular;30" halign="left" position="1000,1025" size="320,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_blue" transparent="1" valign="center" zPosition="1" />

				<widget name="config" position="40,130" size="1200,720" itemHeight="45" enableWrapAround="1" transparent="1" zPosition="9" scrollbarMode="showOnDemand" />
				<widget name="description" position="34,888" size="1214,102" font="Regular; 32" halign="center" foregroundColor="#00ffffff" transparent="1" zPosition="5" />
				<eLabel backgroundColor="#00fffffe" position="40,856" size="1200,3" zPosition="10" />

				<ePixmap blend="blend" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/log.png" position="1354,508" size="512,256" zPosition="5" />

				<ePixmap blend="blend" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/kofi.png" position="1349,778" size="256,256" zPosition="5" />
				<ePixmap blend="blend" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/paypal.png" position="1619,778" size="256,256" zPosition="5" />
				<eLabel name="" position="1362,1031" size="500,45" backgroundColor="#ff000000" halign="center" valign="center" transparent="0" cornerRadius="26" font="Regular; 28" zPosition="1" text="Offer Coffe" foregroundColor="#fe00" />
			</screen>
			'''

	else:
		skin = '''
			<screen name="SetupMaker" position="center,center" size="1920,1080" title="SetupMaker" backgroundColor="#050c101b" flags="wfNoBorder">
				<eLabel backgroundColor="#002d3d5b" cornerRadius="20" position="0,0" size="1920,1080" zPosition="-99" />
				<eLabel backgroundColor="#001a2336" cornerRadius="30" position="20,1014" size="1880,60" zPosition="-80" />
				<eLabel name="" position="31,30" size="1220,977" zPosition="-90" cornerRadius="18" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />

				<!-- /* time -->
				<eLabel name="" position="38,38" size="1207,52" backgroundColor="#00171a1c" halign="center" valign="center" transparent="0" font="Regular; 36" zPosition="1" text="VAVOO MAKER BY LULULLA" foregroundColor="#007fcfff" />

				<widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="1775,25" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="120,40" source="global.CurrentTime" transparent="1">
					<convert type="ClockToText">Default</convert>
				</widget>
				<widget backgroundColor="#00171a1c" font="Regular;34" halign="right" position="1385,25" render="Label" shadowColor="#00000000" shadowOffset="-2,-2" size="400,40" source="global.CurrentTime" transparent="1">
					<convert type="ClockToText">Date</convert>
				</widget>

				<widget source="session.VideoPicture" render="Pig" position="1280,120" zPosition="20" size="622,350" backgroundColor="#ff000000" transparent="0" />

				<eLabel name="" position="20,30" size="1244,977" zPosition="-90" backgroundColor="#00171a1c" foregroundColor="#00171a1c" />
				<eLabel backgroundColor="#002d3d5b" position="0,0" size="1920,1080" zPosition="-1" />
				<eLabel backgroundColor="#001a2336" position="20,1014" size="1880,60" zPosition="-80" />

				<eLabel backgroundColor="#001a2336" position="34,90" size="1220,3" zPosition="10" />
				<ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_red.png" position="32,1029" size="30,30" alphatest="blend" transparent="1" />
				<ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_green.png" position="342,1034" size="30,30" alphatest="blend" transparent="1" />
				<ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_yellow.png" position="652,1034" size="30,30" alphatest="blend" transparent="1" />
				<ePixmap pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/key_blue.png" position="962,1034" size="30,30" alphatest="blend" transparent="1" />

				<widget backgroundColor="#9f1313" font="Regular;30" halign="left" position="65,1025" size="300,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_red" transparent="1" valign="center" zPosition="1" />
				<widget backgroundColor="#1f771f" font="Regular;30" halign="left" position="380,1025" size="300,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_green" transparent="1" valign="center" zPosition="1" />
				<widget backgroundColor="#a08500" font="Regular;30" halign="left" position="685,1025" size="300,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_yellow" transparent="1" valign="center" zPosition="1" />
				<widget backgroundColor="#18188b" font="Regular;30" halign="left" position="1000,1025" size="320,40" render="Label" shadowColor="black" shadowOffset="-2,-2" source="key_blue" transparent="1" valign="center" zPosition="1" />

				<widget name="config" position="40,130" size="1200,720" itemHeight="45" font="Regular; 30" enableWrapAround="1" transparent="1" zPosition="9" scrollbarMode="showOnDemand" />
				<widget name="description" position="34,888" size="1214,102" font="Regular; 32" halign="center" foregroundColor="#00ffffff" transparent="1" zPosition="5" />
				<eLabel backgroundColor="#00fffffe" position="40,856" size="1200,3" zPosition="10" />

				<ePixmap blend="blend" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/log.png" position="1354,508" size="512,256" zPosition="5" />

				<ePixmap blend="blend" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/kofi.png" position="1349,778" size="256,256" zPosition="5" />
				<ePixmap blend="blend" pixmap="/usr/lib/enigma2/python/Plugins/Extensions/vavoo-maker/icons/paypal.png" position="1619,778" size="256,256" zPosition="5" />
				<eLabel name="" position="1362,1031" size="500,45" backgroundColor="#ff000000" halign="center" valign="center" transparent="0" cornerRadius="26" font="Regular; 28" zPosition="1" text="Offer Coffe" foregroundColor="#fe00" />
			</screen>
			'''

	def __init__(self, session):
		Screen.__init__(self, session)
		self.title = _("vavoo playlists") + " - " + choices.get(config.plugins.vavoomaker.current.value, config.plugins.vavoomaker.current.value).title()
		# self.skin = ctrlSkin('SetupMaker', SetupMaker.skin)
		self.enabled = []
		self.process_build = []
		self.vavooFetcher = vavooFetcher()
		self["config"] = SelectionList([], enableWrapAround=True)
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Create bouquets"))
		self["key_yellow"] = StaticText(_("Toggle all"))
		self["key_blue"] = StaticText(_("Remove"))
		self["description"] = StaticText("")
		self["actions"] = ActionMap(
			[
				"SetupActions",
				"ColorActions"
			],
			{
				"ok": self["config"].toggleSelection,
				"save": self.makeBouquets,
				"cancel": self.backCancel,
				"yellow": self["config"].toggleAllSelection,
				"blue": self.deleteBouquets,
			},
			-2
		)
		self.loading_message = _("Downloading playlist - Please wait!")
		self["description"].text = self.loading_message

		self.onClose.append(self.__onClose)

		self.timer = eTimer()
		if hasattr(self.timer, "callback"):
			self.timer.callback.append(self.buildList)
		else:
			if os_path.exists("/usr/bin/apt-get"):
				self.timer_conn = self.timer.timeout.connect(self.buildList)
			print("[Version Check] ERROR: eTimer does not support callback.append()")
		self.timer.start(10, 1)

	def __onClose(self):
		try:
			self.vavooFetcher.cleanup()
		except Exception as e:
			print('Error clean:', e)
			pass

	def buildList(self):
		self["actions"].setEnabled(False)
		self.vavooFetcher.getPlaylist()
		self.process_build = sorted(list(self.vavooFetcher.playlists_processed[config.plugins.vavoomaker.current.value].keys()), key=lambda x: group_titles.get(x, x).lower())
		self.enabled = [x for x in getattr(config.plugins.vavoomaker, config.plugins.vavoomaker.current.value).value.split("|") if x in self.process_build]
		self["config"].setList([SelectionEntryComponent(group_titles.get(x, x), x, "", x in self.enabled) for x in self.process_build])
		self["actions"].setEnabled(True)
		self["description"].text = ""

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
		self.close()

	def backCancel(self):
		self.readList()
		if any([getattr(config.plugins.vavoomaker, choice).isChanged() for choice in choices]):
			self.session.openWithCallback(self.cancelConfirm, MessageBox, _("Really close without saving settings?"))
		else:
			self.close()

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


def PluginMain(session, **kwargs):
	return session.open(SetupMaker)


def Plugins(**kwargs):
	return [PluginDescriptor(name="Vavoo Maker Playlists", description=_("Make IPTV bouquets based on Vavoo List Channels"), where=PluginDescriptor.WHERE_PLUGINMENU, icon="icon.png", needsRestart=True, fnc=PluginMain)]
