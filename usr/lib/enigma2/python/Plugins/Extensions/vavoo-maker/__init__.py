# -*- coding: utf-8 -*-

from __future__ import absolute_import
__author__ = "Lululla"
__email__ = "ekekaz@gmail.com"
__copyright__ = 'Copyright (c) 2024 Lululla'
__license__ = "GPL-v2"
__version__ = "1.0.0"

from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from gettext import gettext, dgettext, bindtextdomain
from os import environ
from os.path import exists


def reload_bouquet():
	from enigma import eDVBDB
	eDVBDB.getInstance().reloadServicelist()
	eDVBDB.getInstance().reloadBouquets()


try:
	from urllib import unquote
except ImportError:
	from urllib.parse import unquote


try:
	import pickle
except:
	from six.moves import cPickle as pickle


PluginLanguageDomain = 'vavoo-maker'
PluginLanguagePath = 'Extensions/vavoo-maker/locale'


isDreambox = False
if exists("/usr/bin/apt-get"):
	isDreambox = True


def localeInit():
	if isDreambox:
		lang = language.getLanguage()[:2]
		environ["LANGUAGE"] = lang
	bindtextdomain(PluginLanguageDomain, resolveFilename(SCOPE_PLUGINS, PluginLanguagePath))


if isDreambox:
	def _(txt):
		return dgettext(PluginLanguageDomain, txt) if txt else ""
else:
	def _(txt):
		translated = dgettext(PluginLanguageDomain, txt)
		if translated:
			return translated
		else:
			print(("[%s] fallback to default translation for %s" % (PluginLanguageDomain, txt)))
			return gettext(txt)

localeInit()
language.addCallback(localeInit)


group_titles = {
	"Albania": "Albania",
	"Arabia": "Arabia",
	"Balkans": "Balkans",
	"Bulgaria": "Bulgaria",
	"Croatia": "Croazia",
	"France": "France",
	"Germany": "Germany",
	"Italy": "Italy",
	"Netherlands": "Netherlands",
	"Poland": "Poland",
	"Portugal": "Portugal",
	"Romania": "Romania",
	"Russia": "Russia",
	"Spain": "Spain",
	"Turkey": "Turkey",
	"United Kingdom": "United Kingdom"
}
