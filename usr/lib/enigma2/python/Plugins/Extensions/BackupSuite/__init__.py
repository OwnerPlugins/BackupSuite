# -*- coding: utf-8 -*-
#
# BackupSuite for Enigma2
# Modified by Lululla - 2026-11-21: version 3.0-r12, translation fallback
#

from __future__ import print_function
from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
import gettext
import os

PluginLanguageDomain = "BackupSuite"
PluginLanguagePath = "Extensions/BackupSuite/locale"
__version__ = "3.0-r12"
LOGFILE = "/tmp/BackupSuite.log"
VERSIONFILE = "imageversion"
ENIGMA2VERSIONFILE = "/tmp/enigma2version"
OFGWRITE_BIN = "/usr/bin/ofgwrite"


def localeInit():
    lang = language.getLanguage()[:2]
    os.environ["LANGUAGE"] = lang
    gettext.bindtextdomain(
        PluginLanguageDomain,
        resolveFilename(
            SCOPE_PLUGINS,
            PluginLanguagePath))


def _(txt):
    translated = gettext.dgettext(PluginLanguageDomain, txt)
    if translated == txt:
        # not translated by the plugin: try the enigma2 catalog
        translated = gettext.gettext(txt)
    return translated


localeInit()
language.addCallback(localeInit)
