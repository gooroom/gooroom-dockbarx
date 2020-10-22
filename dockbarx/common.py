#!/usr/bin/python3
#-*- coding: utf-8 -*-

#   common.py
#
#	Copyright 2008, 2009, 2010 Aleksey Shaferov and Matias Sars
#   Copyright (C) 2019 Gooroom <gooroom@gooroom.kr>
#
#	DockBar is free software: you can redistribute it and/or modify
#	it under the terms of the GNU General Public License as published by
#	the Free Software Foundation, either version 3 of the License, or
#	(at your option) any later version.
#
#	DockBar is distributed in the hope that it will be useful,
#	but WITHOUT ANY WARRANTY; without even the implied warranty of
#	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#	GNU General Public License for more details.
#
#	You should have received a copy of the GNU General Public License
#	along with dockbar.  If not, see <http://www.gnu.org/licenses/>.

import gi
from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import Gio
from gi.repository import GLib

import os
import dbus
from dbus.mainloop.glib import DBusGMainLoop
import xdg.DesktopEntry
from urllib.parse import unquote
from time import time
import weakref
import locale
from .log import logger
import getpass

GSETTINGS_CLIENT = Gio.Settings.new("org.dockbarx")
GSETTINGS_THEMES = Gio.Settings.new("org.dockbarx.themes")
GSETTINGS_DOCK = Gio.Settings.new("org.dockbarx.dock")
GSETTINGS_AWN = Gio.Settings.new("org.dockbarx.awn")
GSETTINGS_APPLETS = Gio.Settings.new("org.dockbarx.applets")
GSETTINGS_DOCK_THEME = GSETTINGS_DOCK.get_child("theme")

DBusGMainLoop(set_as_default=True) # for async calls
BUS = dbus.SessionBus()

def compiz_call_sync(obj_path, func_name, *args):
    # Returns a compiz function call.
    # No errors are dealt with here,
    # error handling are left to the calling function.
    path = "/org/freedesktop/compiz"
    if obj_path:
        path += "/" + obj_path
    obj = BUS.get_object("org.freedesktop.compiz", path)
    iface = dbus.Interface(obj, "org.freedesktop.compiz")
    func = getattr(iface, func_name)
    if func:
        return func(*args)
    return None

def compiz_reply_handler(*args):
    pass

def compiz_error_handler(error, *args):
    logger.warning("Compiz/dbus error: %s" % error)

def compiz_call_async(obj_path, func_name, *args):
    path = "/org/freedesktop/compiz"
    if obj_path:
        path += "/" + obj_path
    obj = BUS.get_object("org.freedesktop.compiz", path)
    iface = dbus.Interface(obj, "org.freedesktop.compiz")
    func = getattr(iface, func_name)
    if func:
        func(reply_handler=compiz_reply_handler,
             error_handler=compiz_error_handler, *args)

def check_program(name):
    for dir in os.environ['PATH'].split(':'):
        prog = os.path.join(dir, name)
        if os.path.exists(prog): return prog

class Connector():
    """A class to simplify disconnecting of signals"""
    def __init__(self):
        self.connections = weakref.WeakKeyDictionary()

    def connect(self, obj, signal, handler, *args):
            sids = self.connections.get(obj, [])
            sids.append(obj.connect(signal, handler, *args))
            self.connections[obj] = sids

    def connect_after(self, obj, signal, handler, *args):
            sids = self.connections.get(obj, [])
            sids.append(obj.connect_after(signal, handler, *args))
            self.connections[obj] = sids

    def disconnect(self, obj):
        sids = self.connections.pop(obj, None)
        while sids:
            try:
                obj.disconnect(sids.pop())
            except:
                raise


class ODict():
    """An ordered dictionary.

    Has only the most needed functions of a dict, not all."""
    def __init__(self, d=[]):
        if not type(d) in (list, tuple):
            raise TypeError(
                        "The argument has to be a list or a tuple or nothing.")
        self.list = []
        for t in d:
            if not type(d) in (list, tuple):
                raise ValueError(
                        "Every item of the list has to be a list or a tuple.")
            if not len(t) == 2:
                raise ValueError(
                        "Every tuple in the list needs to be two items long.")
            self.list.append(t)

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        t = (key, value)
        self.list.append(t)

    def __delitem__(self, key):
        self.remove(key)

    def __len__(self):
        self.list.__len__()

    def __contains__(self, key):
        for t in self.list:
            if t[0] == key:
                return True
        else:
            return False

    def __iter__(self):
        return list(self.keys()).__iter__()

    def __eq__(self, x):
        if type(x) == dict:
            d = {}
            for t in self.list:
                d[t[0]] = t[1]
            return (d == x)
        elif x.__class__ == self.__class__:
            return (self.list == x.list)
        else:
            return (self.list == x)

    def __len__(self):
        return len(self.list)

    def values(self):
        values = []
        for t in self.list:
            values.append(t[1])
        return values

    def keys(self):
        keys = []
        for t in self.list:
            keys.append(t[0])
        return keys

    def items(self):
        return self.list

    def add_at_index(self, index, key, value):
        t = (key, value)
        self.list.insert(index, t)

    def get(self, key, default=None):
        for t in self.list:
            if t[0] == key:
                return t[1]
        return default

    def get_index(self, key):
        for t in self.list:
            if t[0] == key:
                return self.list.index(t)

    def move(self, key, index):
        for t in self.list:
            if key == t[0]:
                self.list.remove(t)
                self.list.insert(index, t)

    def remove(self, key):
        for t in self.list:
            if key == t[0]:
                self.list.remove(t)

    def has_key(self, key):
        for t in self.list:
            if key == t[0]:
                return True
        else:
            return False

class DesktopEntry(xdg.DesktopEntry.DesktopEntry):
    def __init__(self, file_name):
        xdg.DesktopEntry.DesktopEntry.__init__(self, file_name)
        # Quicklist
        self.quicklist = ODict()
        if not "X-Ayatana-Desktop-Shortcuts" in self.content["Desktop Entry"]:
            return
        entries = self.content["Desktop Entry"]["X-Ayatana-Desktop-Shortcuts"]
        entries = entries.split(";")
        for entry in entries:
            sg = self.content.get("%s Shortcut Group" % entry)
            if not sg:
                continue
            lo = locale.getlocale()[0]
            n = "Name[%s]"
            name = sg.get(n % lo) or sg.get(n % lo[:2])
            if name is None:
                for s in sg:
                    if s.startswith("Name[" + lo[:2]):
                        name = sg[s]
                        break
                else:
                    name = sg.get("Name")
            exe = sg.get("Exec")
            if name and exe:
                self.quicklist[name] = exe

    def launch(self, uri=None):
        os.chdir(os.path.expanduser("~"))
        command = self.getExec()
        if command == "":
            return

        # Replace arguments
        if "%i" in command:
            icon = self.getIcon()
            if icon:
                command = command.replace("%i","--icon %s"%icon)
            else:
                command = command.replace("%i", "")
        command = command.replace("%c", self.getName())
        command = command.replace("%k", self.getFileName())
        command = command.replace("%%", "%")
        for arg in ("%d", "%D", "%n", "%N", "%v", "%m", "%M","--view"):
            command = command.replace(arg, "")
        # TODO: check if more unescaping is needed.

        # Parse the uri
        uris = []
        files = []
        if uri:
            uri = str(uri)
            # Multiple uris are separated with newlines
            uri_list = uri.split("\n")
            for uri in uri_list:
                uri = uri.rstrip()
                file = uri

                # Nautilus and zeitgeist don't encode ' and " in uris and
                # that's needed if we should launch with /bin/sh -c
                uri = uri.replace("'", "%27")
                uri = uri.replace('"', "%22")
                uris.append(uri)

                if file.startswith("file://"):
                    file = file[7:]
                file = file.replace("%20","\ ")
                file = unquote(file)
                files.append(file)

        # Replace file/uri arguments
        if "%f" in command or "%u" in command:
            # Launch once for every file (or uri).
            iterlist = list(range(max(1, len(files))))
        else:
            # Launch only one time.
            iterlist = [0]
        for i in iterlist:
            cmd = command
            # It's an assumption that no desktop entry has more than one
            # of "%f", "%F", "%u" or "%U" in it's command. Othervice some
            # files might be launched multiple times with this code.
            if "%f" in cmd:
                try:
                    f = files[i]
                except IndexError:
                    f = ""
                cmd = cmd.replace("%f", f)
            elif "%u" in cmd:
                try:
                    u = uris[i]
                except IndexError:
                    u = ""
                cmd = cmd.replace("%u", u)
            elif "%F" in cmd:
                cmd = cmd.replace("%F", " ".join(files))
            elif "%U" in cmd:
                cmd = cmd.replace("%U", " ".join(uris))
            # Append the files last if there is no rule for how to append them.
            elif files:
                cmd = "%s %s"%(cmd, " ".join(files))

            if "hwp-qt" in cmd:
                _path = cmd.replace("hwp-qt", "")
                #cmd = "cd " + _path + " & /bin/sh -c " + cmd + " &"
                cmd = "gtk-launch hwp-qt.desktop"
                GLib.spawn_command_line_async(cmd)
                return

            logger.info("Executing: %s"%cmd)
            GLib.spawn_command_line_async("/bin/sh -c '%s' &"%cmd)

    def get_quicklist(self):
        return self.quicklist

    def launch_quicklist_entry(self, entry):
        if not entry in self.quicklist:
            return
        cmd = self.quicklist[entry]

        # Nautilus and zeitgeist don't encode ' and " in uris and
        # that's needed if we should launch with /bin/sh -c
        cmd = cmd.replace("'", "%27")
        cmd = cmd.replace('"', "%22")
        cmd = unquote(cmd)
        logger.info("Executing: %s"%cmd)
        GLib.spawn_command_line_async("/bin/sh -c '%s' &"%cmd)

    def getIcon(self, *args):
        try:
            return xdg.DesktopEntry.DesktopEntry.getIcon(self, *args)
        except:
            logger.warning("Couldn't get icon name from a DesktopEntry")
            return None
            
            


class Opacify():
    def __init__(self):
        self.opacifier = None
        self.old_windows = None
        self.sids = {}
        self.globals = Globals()

    def opacify(self, windows, opacifier=None):
        """Add semi-transparency to windows"""
        if type(windows) in [int, int]:
            windows = [windows]
        if windows:
            windows = [str(xid) for xid in windows]
        if windows and windows == self.old_windows:
            self.opacifier = opacifier
            return
        try:
            values = compiz_call_sync("obs/screen0/opacity_values","get")[:]
            matches = compiz_call_sync("obs/screen0/opacity_matches","get")[:]
            self.use_old_call = False
        except:
            # For older versions of compiz
            try:
                values = compiz_call_sync("core/screen0/opacity_values", "get")
                matches = compiz_call_sync("core/screen0/opacity_matches",
                                              "get")
                self.use_old_call = True
            except:
                return
        # If last fade in/out isn't completed abort the rest of it.
        while self.sids:
            GLib.source_remove(self.sids.popitem()[1])

        steps = self.globals.settings["opacify_smoothness"]
        interval = self.globals.settings["opacify_duration"] / steps
        alpha = self.globals.settings["opacify_alpha"]
        use_fade = self.globals.settings["opacify_fade"]
        placeholder = "(title=Placeholder_line_for_DBX)"
        placeholders = [placeholder, placeholder, placeholder]
        rule_base = "(type=Normal|type=Dialog)&%s&!title=Line_added_by_DBX"
        # Remove old opacify rule if one exist
        old_values = []
        for match in matches[:]:
            if "Line_added_by_DBX" in str(match) or \
               "Placeholder_line_for_DBX" in str(match):
                i = matches.index(match)
                matches.pop(i)
                try:
                    old_values.append(max(values.pop(i), alpha))
                except IndexError:
                    pass
        if not self.globals.settings["opacify_fade"]:
            if windows:
                matches.insert(0,
                               rule_base % "!(xid=%s)" % "|xid=".join(windows))
                self.__compiz_call([alpha]+values, matches)
            else:
                self.__compiz_call(values, matches)
            self.opacifier = opacifier
            self.old_windows = windows
            return

        matches = placeholders + matches
        if len(old_values)>3:
            old_values = old_values[0:2]
        while len(old_values)<3:
            old_values.append(alpha)
        min_index = old_values.index(min(old_values))
        max_index = old_values.index(max(old_values))
        if min_index == max_index:
            min_index = 2
        for x in (0,1,2):
            if x != max_index and x != min_index:
                mid_index = x
                break
        if self.old_windows and windows:
            # Both fade in and fade out needed.
            fadeins = [xid for xid in windows if not xid in self.old_windows]
            fadeouts = [xid for xid in self.old_windows if not xid in windows]

            matches[min_index] = rule_base % "!(xid=%s)" % \
                                 "|xid=".join(windows + fadeouts)
            if fadeouts:
                matches[max_index] = \
                               rule_base % "(xid=%s)" % "|xid=".join(fadeouts)
            if fadeins:
                matches[mid_index] = \
                               rule_base % "(xid=%s)" % "|xid=".join(fadeins)
            v = [alpha, alpha, alpha]
            for i in range(1, steps+1):
                if fadeins:
                    v[mid_index] = 100 - ((steps - i) * (100 - alpha) / steps)
                if fadeouts:
                    v[max_index] = 100 - (i*(100-alpha) / steps)
                sid = time()
                if i == 1:
                    self.__compiz_call(v + values, matches)
                else:
                    self.sids[sid] = GLib.timeout_add((i - 1) * interval,
                                                         self.__compiz_call,
                                                         v+values,
                                                         None,
                                                         sid)
        elif windows:
            # Fade in
            matches[max_index] = rule_base % "!(xid=%s)" % \
                                 "|xid=".join(windows) + "_"
            # The "_" is added since matches that change only on a "!" isn't
            # registered. (At least that's what I think.)
            v = [alpha, alpha, alpha]
            v[max_index] = 100
            self.__compiz_call(v + values, matches)
            for i in range(1, steps+1):
                v[max_index] = 100 - ( i * (100 - alpha) / steps)
                sid = time()
                self.sids[sid] = GLib.timeout_add(i * interval,
                                                     self.__compiz_call,
                                                     v + values,
                                                     None,
                                                     sid)
        else:
            # Deopacify
            v = [0, 0, 0]
            for i in range(1, steps):
                value = 100 - ((steps - i) * (100 - alpha) / steps)
                v = [max(value, old_value) for old_value in old_values]
                sid = time()
                self.sids[sid] = GLib.timeout_add(i * interval,
                                                     self.__compiz_call,
                                                     v + values,
                                                     None,
                                                     sid)
            delay = steps * interval + 1
            sid = time()
            v = [100, alpha, alpha]
            self.sids[sid] = GLib.timeout_add(delay,
                                                 self.__compiz_call,
                                                 v + values,
                                                 matches,
                                                 sid)
        self.opacifier = opacifier
        self.old_windows = windows

    def deopacify(self, opacifier=None):
        if opacifier is None or opacifier == self.opacifier:
            self.opacify(None)

    def set_opacifier(self, opacifier):
        if self.opacifier != None:
            self.opacifier = opacifier

    def get_opacifier(self):
        return self.opacifier

    def __compiz_call(self, values=None, matches=None, sid=None):
        if self.use_old_call:
            plugin = "core"
        else:
            plugin = "obs"
        if values is not None:
            compiz_call_async(plugin + "/screen0/opacity_values",
                              "set", values)
        if matches is not None:
            compiz_call_async(plugin + "/screen0/opacity_matches",
                              "set", matches)
        self.sids.pop(sid, None)



class Globals(GObject.GObject):
    """ Globals is a signletron containing all the "global" variables of dockbarx.

    It also keeps track of gconf settings and signals changes in gconf to other programs"""

    __gsignals__ = {
        "color2-changed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,()),
        "show-only-current-desktop-changed": (GObject.SignalFlags.RUN_FIRST,
                                              GObject.TYPE_NONE,()),
        "show-only-current-monitor-changed": (GObject.SignalFlags.RUN_FIRST,
                                              GObject.TYPE_NONE,()),
        "theme-changed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,()),
        "popup-style-changed": (GObject.SignalFlags.RUN_FIRST,
                                GObject.TYPE_NONE,()),
        "color-changed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,()),
        "dockmanager-changed": (GObject.SignalFlags.RUN_FIRST,
                                GObject.TYPE_NONE,()),
        "dockmanager-badge-changed": (GObject.SignalFlags.RUN_FIRST,
                                      GObject.TYPE_NONE,()),
        "badge-look-changed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,()),
        "progress-bar-look-changed": (GObject.SignalFlags.RUN_FIRST,
                                      GObject.TYPE_NONE,()),
        "media-buttons-changed": (GObject.SignalFlags.RUN_FIRST,
                                GObject.TYPE_NONE,()),
        "quicklist-changed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,()),
        "unity-changed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,()),
        "show-tooltip-changed": (GObject.SignalFlags.RUN_FIRST,
                                 GObject.TYPE_NONE,()),
        "show-previews-changed": (GObject.SignalFlags.RUN_FIRST,
                                  GObject.TYPE_NONE,()),
        "preview-size-changed": (GObject.SignalFlags.RUN_FIRST,
                                 GObject.TYPE_NONE,()),
        "window-title-width-changed": (GObject.SignalFlags.RUN_FIRST,
                                       GObject.TYPE_NONE,()),
        "locked-list-in-menu-changed": (GObject.SignalFlags.RUN_FIRST,
                                         GObject.TYPE_NONE,()),
        "locked-list-overlap-changed": (GObject.SignalFlags.RUN_FIRST,
                                         GObject.TYPE_NONE,()),
        "preference-update": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,()),
        "gkey-changed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,()),
        "use-number-shortcuts-changed": (GObject.SignalFlags.RUN_FIRST,
                                         GObject.TYPE_NONE,()),
        "show-close-button-changed": (GObject.SignalFlags.RUN_FIRST,
                                      GObject.TYPE_NONE,()),
        "dock-size-changed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,()),
        "dock-position-changed": (GObject.SignalFlags.RUN_FIRST,
                                      GObject.TYPE_NONE,()),
        "dock-mode-changed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,()),
        "dock-offset-changed": (GObject.SignalFlags.RUN_FIRST,
                                GObject.TYPE_NONE,()),
        "dock-overlap-changed": (GObject.SignalFlags.RUN_FIRST,
                                 GObject.TYPE_NONE,()),
        "dock-behavior-changed": (GObject.SignalFlags.RUN_FIRST,
                                  GObject.TYPE_NONE,()),
        "dock-theme-changed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,()),
        "dock-color-changed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,()),
        "dock-end-decorations-changed": (GObject.SignalFlags.RUN_FIRST,
                                  GObject.TYPE_NONE,()),
        "awn-behavior-changed": (GObject.SignalFlags.RUN_FIRST,
                                  GObject.TYPE_NONE,()),
        "refresh": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE,())
    }

    DEFAULT_SETTINGS = {
          "theme": "Glassified",
          "popup_style_file": "dbx.tar.gz",
          "groupbutton_attention_notification_type": "red",
          "workspace_behavior": "switch",
          "popup_delay": 250,
          "second_popup_delay": 30,
          "popup_align": "center",
          "no_popup_for_one_window": False,
          "show_only_current_desktop": False,
          "show_only_current_monitor": False,
          "preview": False,
          "preview_size": 150,
          "preview_minimized": True,
          "old_menu": False,
          "show_close_button": True,
          "locked_list_in_menu": True,
          "locked_list_no_overlap": False,
          "window_title_width": 140,
          "reorder_window_list": True,

          "select_one_window": "select or minimize window",
          "select_multiple_windows": "select or minimize all",
          "delay_on_select_all": True,
          "select_next_use_lastest_active": False,
          "select_next_activate_immediately": False,

          "dockmanager": False,
          "media_buttons": True,
          "quicklist": True,
          "unity": True,

          "badge_use_custom_font": False,
          "badge_font": "sans 10",
          "badge_custom_bg_color": False,
          "badge_bg_color": "#CDCDCD",
          "badge_bg_alpha": 255,
          "badge_custom_fg_color": False,
          "badge_fg_color": "#020202",
          "badge_fg_alpha": 255,

          "progress_custom_bg_color": False,
          "progress_bg_color": "#CDCDCD",
          "progress_bg_alpha": 64,
          "progress_custom_fg_color": False,
          "progress_fg_color": "#772953",
          "progress_fg_alpha": 255,

          "opacify": False,
          "opacify_group": False,
          "opacify_fade": True,
          "opacify_alpha": 5,
          "opacify_smoothness": 5,
          "opacify_duration": 100,

          "separate_wine_apps": True,
          "separate_prism_apps": True,
          "separate_ooo_apps": True,

          "groupbutton_show_tooltip": False,

          "groupbutton_left_click_action": "select or minimize group",
          "groupbutton_shift_and_left_click_action": "launch application",
          "groupbutton_middle_click_action": "close all windows",
          "groupbutton_shift_and_middle_click_action": "no action",
          "groupbutton_right_click_action": "show menu",
          "groupbutton_shift_and_right_click_action": "no action",
          "groupbutton_scroll_up": "select previous window",
          "groupbutton_scroll_down": "select next window",
          "groupbutton_left_click_double": False,
          "groupbutton_shift_and_left_click_double": False,
          "groupbutton_middle_click_double": False,
          "groupbutton_shift_and_middle_click_double": False,
          "groupbutton_right_click_double": False,
          "groupbutton_shift_and_right_click_double": False,

          "windowbutton_left_click_action": "select or minimize window",
          "windowbutton_shift_and_left_click_action": \
                                            "select or minimize window",
          "windowbutton_middle_click_action": "close window",
          "windowbutton_shift_and_middle_click_action": "no action",
          "windowbutton_right_click_action": "show menu",
          "windowbutton_shift_and_right_click_action": "no action",
          "windowbutton_scroll_up": "shade window",
          "windowbutton_scroll_down": "unshade window",

          "windowbutton_close_popup_on_left_click": True,
          "windowbutton_close_popup_on_shift_and_left_click": False,
          "windowbutton_close_popup_on_middle_click": False,
          "windowbutton_close_popup_on_shift_and_middle_click": False,
          "windowbutton_close_popup_on_right_click": False,
          "windowbutton_close_popup_on_shift_and_right_click": False,
          "windowbutton_close_popup_on_scroll_up": False,
          "windowbutton_close_popup_on_scroll_down": False,

          "gkeys_select_next_group": False,
          "gkeys_select_next_group_keystr": "<super>Tab",
          "gkeys_select_previous_group": False,
          "gkeys_select_previous_group_keystr": "<super><shift>Tab",
          "gkeys_select_next_window": False,
          "gkeys_select_next_window_keystr": "<super><control>Tab",
          "gkeys_select_previous_window": False,
          "gkeys_select_previous_window_keystr": "<super><control><shift>Tab",
          "gkeys_select_next_group_skip_launchers": False,
          "use_number_shortcuts": True,
                      
          "dock/theme_file": "dbx.tar.gz",
          "dock/position": "left",
          "dock/size": 42,
          "dock/offset":0,
          "dock/mode": "panel",
          "dock/behavior": "panel",
          "dock/end_decorations": False,

          "awn/behavior": "disabled"}

    DEFAULT_COLORS={
                      "color1": "#333333",
                      "color1_alpha": 170,
                      "color2": "#FFFFFF",
                      "color3": "#FFFF75",
                      "color4": "#9C9C9C",

                      "color5": "#FFFF75",
                      "color5_alpha": 160,
                      "color6": "#000000",
                      "color7": "#000000",
                      "color8": "#000000",

               }

    def __new__(cls, *p, **k):
        if not "_the_instance" in cls.__dict__:
            cls._the_instance = GObject.GObject.__new__(cls)
        return cls._the_instance

    def __init__(self):
        if not "settings" in self.__dict__:
            # First run.
            GObject.GObject.__init__(self)

            # "Global" variables
            self.gtkmenu_showing = False
            self.opacified = False
            self.opacity_values = None
            self.opacity_matches = None
            self.dragging = False
            self.theme_name = None
            self.popup_style_file = None
            self.default_popup_style = None
            self.dock_colors = {}
            self.__compiz_version = None

            self.set_shown_popup(None)
            self.set_locked_popup(None)
            # Get gconf settings
            self.settings = self.__get_dconf_settings()

            # Set gconf notifiers
            GSETTINGS_CLIENT.connect("changed", self.__on_dconf_changed)
            GSETTINGS_THEMES.connect("changed", self.__on_dconf_changed)
            GSETTINGS_AWN.connect("changed", self.__on_dconf_changed)
            #GSETTINGS_APPLETS.connect("changed", self.__on_dconf_changed)
            GSETTINGS_DOCK.connect("changed", self.__on_dconf_changed)
            GSETTINGS_DOCK_THEME.connect("changed", self.__on_dconf_changed)

            # Change old gconf settings
#            group_button_actions_d = {"select or minimize group": "select",
#                                      "select group": "select",
#                                      "select or compiz scale group": "select"}
#                                           self.settings[name])
#
#            for name, value in self.settings.items():
#                if ("groupbutton" in name) and \
#                   ("click" in name or "scroll" in name) and \
#                   (value in group_button_actions_d):
#                    self.settings[name] = group_button_actions_d[value]
#                    GCONF_CLIENT.set_string(GCONF_DIR + "/" + name,
#                                            self.settings[name])
#            if self.settings.get("workspace_behavior") == "ingore":
#                self.settings["workspace_behavior"] = "ignore"
#                GCONF_CLIENT.set_string(GCONF_DIR + "/workspace_behavior",
#                                        "ignore")

            self.colors = {}

    def get_settings_from_path(self, path):
        entry = path
        gst = GSETTINGS_CLIENT
        if entry.split("/")[-2] == "dock":
            gst = gst.get_child("dock")
            try:
                if entry.split("/")[-3] == "theme":
                    gst = gst.get_child("theme")
            except:
                return gst
        elif entry.split("/")[-2] == "awn":
            gst = gst.get_child("awn")
        elif entry.split("/")[-2] == "applets":
            gst = gst.get_child("applets")
        elif entry.split("/")[-2] == "themes":
            gst = gst.get_child("themes")
        elif len(entry.split("/")) == 4 and \
            entry.split("/")[-2] == "dockbarx":
            return gst
        else:
            return None
        return gst

    def __on_dconf_changed(self, settings, keyname):
        if keyname == 'refresh':
            refresh = settings.get_boolean(keyname)
            if refresh:
                settings.set_boolean(keyname, False)
                self.emit("refresh")
            return
        pref_update = False
        changed_settings = []
        key = keyname.replace("-", "_")
        settings_id = settings.props.schema_id

        if settings_id.split(".")[-1] == "dock":
            key = "dock/" + key
        elif settings_id.split(".")[-1] == "awn":
            key = "awn/" + key
        elif settings_id.split(".")[-1] == "applets":
            key = "applets/" + key
        elif settings_id.split(".")[-1] == "theme":
            key = "dock/theme/" + key
        elif len(settings_id.split("."))>=3 and \
              settings_id.split(".")[-3] == "applets":
                  # Ignore applet settings
                  return
        
        entry_get = {str: settings.get_string,
                            bool: settings.get_boolean,
                            int: settings.get_int }

        if key in self.settings:
            value = self.settings[key]
            if entry_get[type(value)](keyname) != value:
                changed_settings.append(key.replace('_', '-'))
                self.settings[key] = entry_get[type(value)](keyname)
                pref_update = True

        # Theme colors and popup style
        if self.theme_name:
            theme_name = self.theme_name.replace(" ", "_").encode()
            try:
                theme_name = theme_name.translate(None, '!?*()/#"@')
            except:
                pass
            #psf = "org/dockbarx/themes/popup-style-file"
            #if entry == psf:
            if keyname == "popup-style-file":
                value = settings.get_string(keyname)
                if self.popup_style_file != value:
                    self.popup_style_file = value
                    pref_update == True
                    self.emit("popup-style-changed")

            if settings.props.path == "/org/dockbarx/themes/":
                for i in range(1, 9):
                    c = "color%s"%i
                    a = "color%s_alpha"%i
                    for k in (c, a):
                        if keyname.replace("-", "_") == k:
                            value = self.colors[k]
                            if entry_get[type(value)](keyname) != value:
                                changed_settings.append(keyname)
                                self.colors[k] = entry_get[type(value)](keyname)
                                pref_update = True

        # Dock theme colors
        tf = self.settings["dock/theme_file"]
        theme_file = GSETTINGS_DOCK.get_string("theme-file")
        if tf == GSETTINGS_DOCK.get_string("theme-file"):
            dts = GSETTINGS_DOCK.get_child("theme")
            for key, value in list(self.dock_colors.items()):
                if keyname.replace("-", "_") == key:
                    if entry_get[type(value)] != value:
                        self.dock_colors[key] = entry_get[type(value)](keyname)
                        self.emit("dock-color-changed")
                        pref_update = True

        #TODO: Add check for sane values for critical settings.
        if "dock/size" in changed_settings:
            self.emit("dock-size-changed")
        if "dock/offset" in changed_settings:
            self.emit("dock-offset-changed")
        if "dock/position" in changed_settings:
            self.emit("dock-position-changed")
        if "dock/behavior" in changed_settings:
            self.emit("dock-behavior-changed")
        if "dock/mode" in changed_settings:
            self.emit("dock-mode-changed")
        if "dock/end-decorations" in changed_settings:
            self.emit("dock-end-decorations-changed")
        if "dock/theme-file" in changed_settings:
            self.emit("dock-theme-changed")
        if "awn/behavior" in changed_settings:
            self.emit("awn-behavior-changed")
        if "locked-list-no-overlap" in changed_settings:
            self.emit("locked-list-overlap-changed")
        if "locked_list_in_menu" in changed_settings:
            self.emit("locked-list-in-menu-changed")
        if "color2" in changed_settings:
            self.emit("color2-changed")
        if "show-only-current-desktop" in changed_settings:
            self.emit("show-only-current-desktop-changed")
        if "show-only-current-monitor" in changed_settings:
            self.emit("show-only-current-monitor-changed")
        if "preview" in changed_settings:
            self.emit("show-previews-changed")
        if "preview-size" in changed_settings:
            self.emit("preview-size-changed")
        if "window-title-width" in changed_settings:
            self.emit("window-title-width-changed")
        if "groupbutton-show-tooltip" in changed_settings:
            self.emit("show-tooltip-changed")
        if "show-close-button" in changed_settings:
            self.emit("show-close-button-changed")
        if "media-buttons" in changed_settings:
            self.emit("media-buttons-changed")
        if "quicklist" in changed_settings:
            self.emit("quicklist-changed")
        if "unity" in changed_settings:
            self.emit("unity-changed")
        if "dockmanager" in changed_settings:
            self.emit("dockmanager-changed")
        if "use-number-shortcuts" in changed_settings:
            self.emit("use-number-shortcuts-changed")
        for key in changed_settings:
            if key == "theme":
                self.emit("theme-changed")
            if key.startswith("color"):
                self.emit("color-changed")
            if "gkey" in key:
                self.emit("gkey-changed")
            if key.startswith("badge"):
                self.emit("badge-look-changed")
            if key.startswith("progress"):
                self.emit("progress-bar-look-changed")

        if pref_update == True:
            self.emit("preference-update")

    def __add_values_in_settings(self, schema, settings, path = ''):
        names = schema.list_keys()
        for name in names:
            value = schema.get_value(name)
            value_type = value.get_type_string()
            # dconf의 key는 "-"만 허용
            name = name.replace("-", "_")
            name = path + name
            if 's' == value_type:
                settings[name] = value.get_string()
            elif 'i' == value_type:
                settings[name] = value.get_int32()
            elif 'b' == value_type:
                settings[name] = value.get_boolean()
            elif 'as' == value_type and name != "launchers":
                settings[name] = value.get_strv()
            
        # add child schemas
        children = schema.list_children()
        if bool(children):
            for name in children:
                child = schema.get_child(name)
                childpath = path + name + "/"
                self.__add_values_in_settings(child, settings, childpath)
        pass


    def __get_dconf_settings(self):
        settings = {}
        self.__add_values_in_settings(GSETTINGS_CLIENT, settings)
        return settings

    def update_colors(self, theme_name, theme_colors=None, theme_alphas=None):
        # Updates the colors when the theme calls for an update.
        if theme_name is None:
            self.colors.clear()
            # If there are no theme name, preference window wants empty colors.
            for i in range(1, 9):
                self.colors["color%s"%i] = "#000000"
            return

        theme_name = theme_name.replace(" ", "_")
        for sign in ("'", '"', "!", "?", "*", "(", ")", "/", "#", "@"):
            theme_name = theme_name.replace(sign, "")

        # add name
        GSETTINGS_THEMES = GSETTINGS_CLIENT.get_child("themes")
        #GSETTINGS_THEMES.set_string("name", theme_name.replace("_", "-"))
        self.colors.clear()

        for i in range(1, 9):
            c = "color%s"%i
            a = "color%s_alpha"%i
            cv = GSETTINGS_THEMES.get_string(c)
            if len(cv) > 0:
                self.colors[c] = cv
            else:
                if c in theme_colors:
                    self.colors[c] = theme_colors[c]
                else:
                    self.colors[c] = self.DEFAULT_COLORS[c]
                GSETTINGS_THEMES.set_string(c , self.colors[c].replace("_", "-"))

            av = GSETTINGS_THEMES.get_int(a.replace("_", "-"))
            if av > -1:
                self.colors[a] = av
            else:
                if c in theme_alphas:
                    if "no" in theme_alphas[c]:
                        continue
                    else:
                        alpha = int(theme_alphas[c])
                        self.colors[a] = int(round(alpha * 2.55))
                elif a in self.DEFAULT_COLORS:
                    self.colors[a] = self.DEFAULT_COLORS[a]
                else:
                    continue
                GSETTINGS_THEMES.set_int(a.replace("_", "-") , self.colors[a])

    def update_popup_style(self, theme_name, default_style):
        # Runs when the theme has changed.
        self.default_popup_style = default_style
        theme_name = theme_name.replace(" ", "_")
        for sign in ("'", '"', "!", "?", "*", "(", ")", "/", "#", "@"):
            theme_name = theme_name.replace(sign, "")
        psf = "popup-style-file"
        try:
            style = GSETTINGS_THEMES.get_value(psf).get_string()
            if style != self.popup_style_file:
                self.popup_style_file = style
                self.emit("popup-style-changed")
        except:
            self.popup_style_file = default_style
            GSETTINGS_THEMES.set_string(psf, default_style.replace("_", "-"))
            self.emit("popup-style-changed")
        self.emit("preference-update")

    def set_popup_style(self, style):
        # Used when the popup style is reloaded.
        if self.popup_style_file != style:
            self.popup_style_file = style
            theme_name = self.theme_name
            if theme_name is None:
                return
            theme_name = theme_name.replace(" ", "_").encode()
            for sign in ("'", '"', "!", "?", "*", "(", ")", "/", "#", "@"):
                theme_name = theme_name.replace(sign, "")
            psf = "popup-style-file"
            GSETTINGS_THEMES.set_string(psf, style.replace("_", "-"))
            self.emit("preference-update")

    def set_dock_theme(self, theme, colors):
        gdt = GSETTINGS_DOCK.get_child('theme') # gsettings dockbarx/dock/theme
        gdt_set = {'i': gdt.get_int,
                        's': gdt.get_string }
        if self.settings["dock/theme_file"] != theme:
            self.settings["dock/theme_file"] = theme
            GSETTINGS_DOCK.set_string("theme-file", theme.replace("_", "-"))
        for key, value in list(colors.items()):
            try:
                self.dock_colors[key.replace('-', '_')] = gdt_set[gdt.get_value(key).get_type_string()](key)
            except:
                self.dock_colors[key] = value
                gset = {str: gdt.set_string,
                        int: gdt.set_int }[type(value)]
                #gset("%s/%s" % (gdt, key), value)
                gset(key.replace("_", "-"), value)
        self.emit("preference-update")

    def get_apps_from_gst(self):
        #dconf_launcher_apps = Gio.Settings.default_value(GCONF_DIR + "/launcher") #gsettings = Gio.Settings.new_with_path('org.dockbar.dock', '/mypath/')
        return dconf_launcher_apps

    def get_launcher_apps_from_dconf(self):
        # Get list of pinned_apps
        dconf_launcher_apps = []
        try:
            dconf_launcher_apps = GSETTINGS_CLIENT.get_strv('launchers')

        except:
            GSETTINGS_CLIENT.set_strv('launchers', dconf_launcher_apps)
        return dconf_launcher_apps

    def set_launcher_apps_list(self, pinned_apps):
        GSETTINGS_CLIENT.set_strv("launchers", pinned_apps)
        #params = '['
        #for app in pinned_apps:
        #    params += '{}'.format(app)
        #if params[-1] == ',':
        #    params = params[:-1]
        #params == ']'
        #cmd =   

    def set_shown_popup(self, popup):
        if popup is None:
            self.shown_popup = lambda: None
        else:
            self.shown_popup = weakref.ref(popup)

    def get_shown_popup(self):
        return self.shown_popup()

    def set_locked_popup(self, popup):
        if popup is None:
            self.locked_popup = lambda: None
        else:
            self.locked_popup = weakref.ref(popup)

    def get_locked_popup(self):
        return self.locked_popup()

    def get_compiz_version(self):
        if self.__compiz_version is None:
            try:
                import ccm
                self.__compiz_version = ccm.Version
            except:
                self.__compiz_version = "0.8"
        return self.__compiz_version
        


__connector = Connector()
connect = __connector.connect
connect_after = __connector.connect_after
disconnect = __connector.disconnect

__opacify_obj = Opacify()
opacify = __opacify_obj.opacify
deopacify = __opacify_obj.deopacify
set_opacifier = __opacify_obj.set_opacifier
get_opacifier = __opacify_obj.get_opacifier
