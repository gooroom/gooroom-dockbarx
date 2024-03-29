#!/usr/bin/python3

#   DockbarX applets
#
#	Copyright 2011 Matias Sars
#   Copyright (C) 2019 Gooroom <gooroom@gooroom.kr>
#
#	DockbarX is free software: you can redistribute it and/or modify
#	it under the terms of the GNU General Public License as published by
#	the Free Software Foundation, either version 3 of the License, or
#	(at your option) any later version.
#
#	DockbarX is distributed in the hope that it will be useful,
#	but WITHOUT ANY WARRANTY; without even the implied warranty of
#	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#	GNU General Public License for more details.
#
#	You should have received a copy of the GNU General Public License
#	along with dockbar.  If not, see <http://www.gnu.org/licenses

import gi
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import Gio
from gi.repository import GLib

import os
import imp
import dbus
import weakref
from dbus.mainloop.glib import DBusGMainLoop
from .log import logger

GSETTINGS_APPLETS = Gio.Settings.new("org.dockbarx.applets")

DBusGMainLoop(set_as_default=True) # for async calls
BUS = dbus.SessionBus()
           
class DockXApplets():
    def __init__(self):
        self.find_applets()

    def find_applets(self):
        # Reads the themes from /usr/share/dockbarx/themes/dock_themes and
        # ~/.dockbarx/themes/dock_themes and returns a dict
        # of the theme file names and paths so that a theme can be loaded
        self.applets = {}
        home_folder = os.path.expanduser("~")
        theme_folder = home_folder + "/.dockbarx/applets"
        dirs = ["/usr/share/dockbarx/applets", theme_folder]
        for dir in dirs:
            if not(os.path.exists(dir) and os.path.isdir(dir)):
                continue
            for f in os.listdir(dir):
                name, ext = os.path.splitext(os.path.split(f)[-1])
                if not(ext.lower() == ".applet"):
                    continue
                path = os.path.join(dir, f)
                applet, err = self.read_applet_file(path)
                if err is not None:
                    logger.debug("Error: Did not load applet from %s")
                    logger.debug(err)
                    continue
                name = applet["name"]
                applet["dir"] = dir
                self.applets[name] = applet

    def read_applet_file(self, path):
        f = open(path)
        try:
            lines = f.readlines()
        except:
            lines = None
        finally:
            f.close()
        if not lines or not lines[0].lower().strip() == "@dbx applet":
            text = "Applet at %s doesn't seem to be a dbx applet" % path
            return None, text
        description_nr = None
        settings = {}
        for i in range(len(lines)):
            line = lines[i]
            if line.strip().lower() == "@description":
                description_nr = i + 1
                break
            # Split at "=" and clean up the key and value
            if not "=" in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip().lstrip().lower()
            value = value.strip().lstrip()
            # Remove comments
            if "#" in key:
                continue
            # If there is a trailing comment, remove it
            # But avoid removing # if it's in a quote
            sharp = value.find("#")
            if sharp != -1 and value.count("\"", 0, sharp) % 2 == 0 and \
               value.count("'", 0, sharp) % 2 == 0:
                   value = value.split("#", 1)[0].strip()
            # Remove quote signs
            if value[0] in ("\"", "'") and value[-1] in ("\"", "'"):
                value = value[1:-1]
            
            if key == "name":
                name = value
            settings[key] = value
        if "name" not in settings:
            text = "The applet in file %s has no name" % path
            return None, text
        if "exec" not in settings:
            text = "Applet %s in file %s has no exec" % (name, path)
            return None, text
        if description_nr is None or description_nr >= len(lines):
            text = "Applet %s in file %s has no description" % (name, path)
            return None, text
        settings["description"] =  "\n".join(lines[description_nr:])
        return settings, None

    def get(self, name):
        e = self.applets[name]["exec"]
        iname, ext = os.path.splitext(os.path.split(e)[-1])
        path = os.path.join(self.applets[name]["dir"], e)
        try:
            applet = imp.load_source(iname, path)
        except:
            message = "Error: Could not load applet from %s. " % path
            message += "Could not import the script."
            logger.exception(message)
            return
        return applet

    def get_description(self, name):
        try:
            return self.applets[name]["description"]
        except:
            return ""

    def get_list(self):
        try:
            old_list = GSETTINGS_APPLETS.get_strv("applet-list")
        except:
            raise
            GSETTINGS_APPLETS.set_strv("applet-list", ["DockbarX"])
            return ["DockbarX"]
        all_applets = list(self.applets.keys()) + ["DockbarX", "Spacer"]
        applet_list = [a for a in old_list if a in all_applets]
        if not "DockbarX" in applet_list:
            applet_list.append("DockbarX")
        if applet_list != old_list:
            GSETTINGS_APPLETS.set_strv("applet-list", applet_list)

        return applet_list

    def get_unused_list(self):
        try:
            applet_list = GSETTINGS_APPLET.get_strv("applet-list")
        except:
            GSETTINGS_APPLETS.set_strv("applet-list", ["DockbarX"])
            applet_list = ["DockbarX"]
        all_applets = list(self.applets.keys())
        unused_applets = [a for a in all_applets if a not in applet_list]
        # There should be totally two spacers.
        while (unused_applets + applet_list).count("Spacer") < 2:
            unused_applets.append("Spacer")
        return unused_applets
        
        
    def set_list(self, applet_list):
        all_applets = list(self.applets.keys()) + ["DockbarX", "Spacer"]
        applet_list = [a for a in applet_list if a in all_applets]
        if not "DockbarX" in applet_list:
            applet_list.append("DockbarX")
        GSETTINGS_APPLETS.set_strv(GCONF_DIR+"/applets/applet-list", applet_list)

# Functions used by both DockXApplet and DockXAppletDialog
def set_setting(key, value, list_type=None, applet_name=None):
    if applet_name is None:
        return
    gdir = "%s/applets/%s" % (GCONF_DIR, applet_name)
    gsettings_set = { str: GSETTINGS_APPLETS.set_string,
                  bool: GSETTINGS_APPLETS.set_bool,
                  float: GSETTINGS_APPLETS.set_float,
                  int: GSETTINGS_APPLETS.set_int }
    if type(value) == list:
        list_types = { str: GLib.VariantType.b,
                       bool: gconf.VALUE_BOOL,
                       float: gconf.VALUE_FLOAT,
                       int: gconf.VALUE_INT }
        if len(value) == 0:
            if type(list_type) in list_types:
                lt = list_types[type(list_type)]
            else:
                lt = GSETTINGS_APPLETS.set_string
        else:
            for v in values:
                if v != value[0]:
                    raise ValueError(
                        "All values in the list must be of the same sort")
            lt = list_types[type(value[0])]
        GSETTINGS_APPLETS.set_strv(GCONF_DIR + "/applets/applet-list",
                              list_types, VALUE)
        
    else:
        if type(value) not in gconf_set:
            raise ValueError(
                    "The value must be a string, bool, int or list")
        gsettings_set[type(value)](key, value)
        

def get_setting(key, default=None, applet_name=None):
    if applet_name is None:
        return
    gdir = "%s/applets/%s" % (GCONF_DIR, applet_name)
    try:
        value = GSETTINGS_APPLETS.get_value("%s/%s" % (gdir, key))
    except:
        if default is not None:
            set_setting(key, default, applet_name=applet_name)
        return default
    return value


def get_value(value):
    if value.type == gconf.VALUE_LIST:
        return [get_value(item) for item in value.get_strv()]
    else:
        return {
                "string": value.get_string,
                "int": value.get_int,
                "float": value.get_float,
                "bool": value.get_bool,
                "list": value.get_list
               }[value.type.value_nick]()

class DockXApplet(Gtk.EventBox):
    """This is the base class for DockX applets"""
    
    __gsignals__ = {"clicked": (GObject.SignalFlags.RUN_FIRST,
                                GObject.TYPE_NONE,(Gdk.Event, )),
                    "enter-notify-event": "override",
                    "leave-notify-event": "override",
                    "button-release-event": "override",
                    "button-press-event": "override"}

    def __init__(self, dbx_dict):
        self.dockx_r = weakref.ref(dbx_dict["dock"])
        self.APPLET_NAME = dbx_dict["name"].lower().replace(" ", "")
        Gtk.EventBox.__init__(self)
        self.set_visible_window(False)
        self.set_no_show_all(True)
        self.mouse_pressed = False
        self.expand = False
        # Set gconf notifiers
        gdir = "%s/applets/%s" % (GCONF_DIR, self.APPLET_NAME)
        #GCONF_CLIENT.add_dir(gdir, gconf.CLIENT_PRELOAD_NONE)
        #GCONF_CLIENT.notify_add(gdir, self.__on_gconf_changed, None)
        GSETTINGS_APPLETS.connect("changed", self.__on_gconf_changed)

    def get_setting(self, *args, **kwargs):
        kwargs["applet_name"]=self.APPLET_NAME
        return get_setting(*args, **kwargs)

    def set_setting(self, *args, **kwargs):
        kwargs["applet_name"]=self.APPLET_NAME
        return set_setting(*args, **kwargs)

    def on_setting_changed(self, key, value):
        # Method to be overridden by applet.
        pass

    def __on_gconf_changed(self, client, par2, entry, par4):
        if entry.get_value() is None:
            return
        key = entry.get_key().split("/")[-1]
        value = get_value(entry.get_value())
        self.on_setting_changed(key, value)

    def update(self):
        # Method to be overriden by applet.
        pass

    def get_full_size(self):
        if self.dockx_r:
            dockx = self.dockx_r()
            rel_size = float(dockx.theme.get("rel_size", 100))
            size = dockx.globals.settings["dock/size"]
            return max(size, int(size * rel_size / 100))

    
    def get_size(self):
        if self.dockx_r:
            return self.dockx_r().globals.settings["dock/size"]

    def get_position(self):
        if self.dockx_r:
            return self.dockx_r().globals.settings["dock/position"]

    def get_monitor(self):
        if self.dockx_r:
            return self.dockx_r().monitor

    def get_expand(self):
        return self.expand
        
    def get_applet_size(self):
        if not self.dockx_r:
            return 0
        if not self.get_visible():
            return 0
        if self.get_position() in ("top", "bottom"):
            return self.get_allocation().width
        else:
            return self.get_allocation().height

    def set_expand(self, expand):
        self.expand = expand

    def do_button_release_event(self, event):
        if self.mousepressed:
            self.emit("clicked", event)
        self.mousepressed=False

    def do_button_press_event(self, event):
        self.mousepressed = True
    
    def do_leave_notify_event(self, *args):
        self.mousepressed = False

    def do_enter_notify_event(self, *args):
        pass
        

class DockXAppletDialog(Gtk.Dialog):
    Title = "Applet Preferences"
    def __init__(self, name, t=None, flags=0,
                 buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)):
        if not name:
            logger.error("Error: DockXAppletDialog can't be initialized" \
                         "without a name as it's first argument")
        self.APPLET_NAME = name.lower().replace(" ", "")
        if t is None:
            t = self.Title
        Gtk.Dialog.__init__(self, _(t), None, flags, buttons)

    def get_setting(self, *args, **kwargs):
        kwargs["applet_name"]=self.APPLET_NAME
        return get_setting(*args, **kwargs)

    def set_setting(self, *args, **kwargs):
        kwargs["applet_name"]=self.APPLET_NAME
        return set_setting(*args, **kwargs)
