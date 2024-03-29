#!/usr/bin/python3
#-*- coding: utf-8 -*-

#   windowbutton.py
#
#	Copyright 2008, 2009, 2010 Aleksey Shaferov and Matias Sars
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
#	along with dockbar.  If not, see <http://www.gnu.org/licenses/>.

import gi
from gi.repository import Gtk
from gi.repository import GObject
from gi.repository import GdkPixbuf
from gi.repository import Pango
from gi.repository import Wnck
from gi.repository import GLib

import weakref
import gc
gc.enable()

### use set_preview
from Xlib import X
from Xlib.display import Display
from PIL import Image

from .common import ODict, Globals, Opacify
from .common import connect, disconnect, opacify, deopacify
from .cairowidgets import *
from .log import logger

from . import i18n
_ = i18n.language.gettext

try:
    WNCK_WINDOW_ACTION_MINIMIZE = Wnck.WindowActions.MINIMIZE
    WNCK_WINDOW_ACTION_UNMINIMIZE = Wnck.WindowActions.UNMINIMIZE
    WNCK_WINDOW_ACTION_MAXIMIZE = Wnck.WindowActions.MAXIMIZE
    WNCK_WINDOW_STATE_MINIMIZED = Wnck.WindowState.MINIMIZED
except:
    WNCK_WINDOW_ACTION_MINIMIZE = 1 << 12
    WNCK_WINDOW_ACTION_UNMINIMIZE = 1 << 13
    WNCK_WINDOW_ACTION_MAXIMIZE = 1 << 14
    WNCK_WINDOW_STATE_MINIMIZED = 1 << 0

class Window():
    def __init__(self, wnck_window, group):
        self.group_r = weakref.ref(group)
        self.globals = Globals()
        self.opacify_obj = Opacify()
        connect(self.globals, "show-only-current-monitor-changed",
                             self.__on_show_only_current_monitor_changed)
        self.screen = Wnck.Screen.get_default()
        self.wnck = wnck_window
        self.deopacify_sid = None
        self.opacify_sid = None
        self.select_sid = None
        self.xid = self.wnck.get_xid()
        self.is_active_window = False
        self.on_current_desktop = self.is_on_current_desktop()
        self.monitor = self.get_monitor()

        self.state_changed_event = self.wnck.connect("state-changed",
                                                self.__on_window_state_changed)
        self.icon_changed_event = self.wnck.connect("icon-changed",
                                                self.__on_window_icon_changed)
        self.name_changed_event = self.wnck.connect("name-changed",
                                                self.__on_window_name_changed)
        self.geometry_changed_event = self.wnck.connect("geometry-changed",
                                                self.__on_geometry_changed)
        self.item = WindowItem(self, group)
        self.needs_attention = self.wnck.needs_attention()
        self.item.show()
        self.__on_show_only_current_monitor_changed()

    def __ne__(self, window):
        if isinstance(window, wnck.Window):
            return self.wnck != window
        else:
            return window is not self

    def __eq__(self, window):
        if isinstance(window, Wnck.Window):
            return self.wnck == window
        else:
            return window is self

    def set_active(self, mode):
        if self.is_active_window != mode:
            self.is_active_window = mode
            self.item.active_changed()

    def is_on_current_desktop(self):
        aws = self.screen.get_active_workspace()
        if (self.wnck.get_workspace() is None or \
           self.wnck.get_workspace() == aws) and \
           self.wnck.is_in_viewport(aws):
            return True
        else:
            return False

    def get_monitor(self):
        if not self.globals.settings["show_only_current_monitor"]:
            return 0
        gdk_screen = gtk.gdk.screen_get_default()
        x, y, w, h = self.wnck.get_geometry()
        return gdk_screen.get_monitor_at_point(x + (w / 2), y  + (h / 2))

    def destroy(self):
        if self.deopacify_sid:
            GLib.source_remove(self.deopacify_sid)
            self.deopacify()
        self.remove_delayed_select()

        self.item.clean_up()
        self.item.destroy()
        self.wnck.disconnect(self.state_changed_event)
        self.wnck.disconnect(self.icon_changed_event)
        self.wnck.disconnect(self.name_changed_event)
        if self.geometry_changed_event is not None:
            self.wnck.disconnect(self.geometry_changed_event)
        del self.screen
        del self.wnck
        del self.globals

    def __on_show_only_current_monitor_changed(self, arg=None):
        self.monitor = self.get_monitor()

    def select_after_delay(self, delay):
        if self.select_sid:
            GLib.source_remove(self.select_sid)
        self.select_sid = GLib.timeout_add(delay, self.action_select_window)

    def remove_delayed_select(self):
        if self.select_sid:
            GLib.source_remove(self.select_sid)
            self.select_sid = None

    #### Windows's Events
    def __on_window_state_changed(self, wnck_window,changed_mask, new_state):
        if WNCK_WINDOW_STATE_MINIMIZED & changed_mask:
            self.item.minimized_changed()
            self.group_r().button.update_state_if_shown()

        # Check if the window needs attention
        if self.wnck.needs_attention() != self.needs_attention:
            self.needs_attention = self.wnck.needs_attention()
            self.item.needs_attention_changed()
            self.group_r().needs_attention_changed()

    def __on_window_icon_changed(self, window):
        self.item.icon_changed()

    def __on_window_name_changed(self, window):
        self.item.name_changed()

    def __on_geometry_changed(self, *args):
        group = self.group_r()
        if self.globals.settings["show_only_current_monitor"]:
            monitor = self.get_monitor()
            if monitor != self.monitor:
                self.monitor = monitor
                self.item.update_show_state()
                group.window_monitor_changed()
        if self.globals.settings["show_only_current_desktop"]:
            onc = self.is_on_current_desktop()
            if self.on_current_desktop != onc:
                self.on_current_desktop = onc
                self.item.update_show_state()
                group.window_desktop_changed()
        if self.globals.settings["preview"]:
            self.item.update_preview()

    def desktop_changed(self):
        self.on_current_desktop = self.is_on_current_desktop()
        if self.on_current_desktop:
            self.item.show()
        else:
            self.item.hide()

    #### Opacify
    def opacify(self):
        self.xid = self.wnck.get_xid()
        opacify(self.xid, self.xid)

    def deopacify(self):
        if self.item.deopacify_sid:
            GLib.source_remove(self.item.deopacify_sid)
            self.item.deopacify_sid = None
        if self.deopacify_sid:
            self.deopacify_sid = None
        deopacify(self.xid)

    #### Actions
    def action_select_or_minimize_window(self, widget=None,
                                         event=None, minimize=True):
        # The window is activated, unless it is already
        # activated, then it's minimized. Minimized
        # windows are unminimized. The workspace
        # is switched if the window is on another
        # workspace.
        self.remove_delayed_select()
        if event:
            t = event.time
        else:
            t = 0
        if self.wnck.get_workspace() is not None \
        and self.screen.get_active_workspace() != self.wnck.get_workspace():
            self.wnck.get_workspace().activate(t)
        if not self.wnck.is_in_viewport(self.screen.get_active_workspace()):
            win_x,win_y,win_w,win_h = self.wnck.get_geometry()
            self.screen.move_viewport(win_x-(win_x%self.screen.get_width()),
                                      win_y-(win_y%self.screen.get_height()))
            # Hide popup since mouse movment won't
            # be tracked during compiz move effect
            # which means popup list can be left open.
            group = self.group_r()
            group.popup.hide()
        if self.wnck.is_minimized():
            self.wnck.unminimize(t)
        elif self.wnck.is_active() and minimize:
            self.wnck.minimize()
        else:
            self.wnck.activate(t)
        # Deopacify is needed here since this function is called from
        # the group button class as well.
        self.deopacify()

    def action_select_window(self, widget = None, event = None):
        self.action_select_or_minimize_window(widget, event, False)

    def action_close_window(self, widget=None, event=None):
        if event:
            t = event.time
        else:
            t = 0
        self.wnck.close(t)

    def action_maximize_window(self, widget=None, event=None):
        if self.wnck.is_maximized():
            self.wnck.unmaximize()
        else:
            self.wnck.maximize()

    def action_shade_window(self, widget, event):
        self.wnck.shade()

    def action_unshade_window(self, widget, event):
        self.wnck.unshade()

    def action_show_menu(self, widget, event):
        self.item.show_menu(event)

    def action_minimize_window(self, widget=None, event=None):
        if self.wnck.is_minimized():
            if event:
                t = event.time
            else:
                t = 0
            self.wnck.unminimize(t)
        else:
            self.wnck.minimize()

    def action_none(self, widget=None, event=None):
        pass

    action_function_dict = ODict((
                                  ("select or minimize window",
                                            action_select_or_minimize_window),
                                  ("select window", action_select_window),
                                  ("maximize window", action_maximize_window),
                                  ("close window", action_close_window),
                                  ("show menu", action_show_menu),
                                  ("shade window", action_shade_window),
                                  ("unshade window", action_unshade_window),
                                  ("no action", action_none)
                                ))


class WindowItem(CairoButton):
    __gsignals__ = {
                    "enter-notify-event" : "override", 
                    "leave-notify-event" : "override",
                    "button-press-event": "override",
                    "scroll-event": "override",
                    "clicked": "override",
                    "drag-motion" : "override",
                    "drag-leave" : "override"}

    def __init__(self, window, group):
        CairoButton.__init__(self)
        self.set_no_show_all(True)

        self.window_r = weakref.ref(window)
        self.group_r = weakref.ref(group)
        self.globals = Globals()

        self.opacify_sid = None
        self.deopacify_sid = None
        self.press_sid = None
        self.pressed = False

        self.close_button = CairoCloseButton()
        self.close_button.set_no_show_all(True)
        if self.globals.settings["show_close_button"]:
            self.close_button.show()
        self.label = Gtk.Label()
        self.label.set_ellipsize(Pango.EllipsizeMode.END)
        self.label.set_alignment(0, 0.5)
        self.__update_label()
        self.area.set_needs_attention(window.wnck.needs_attention())
        hbox = Gtk.HBox()
        icon = window.wnck.get_mini_icon()
        self.icon_image = Gtk.Image.new_from_pixbuf(icon)
        hbox.pack_start(self.icon_image, False, True, 0)
        hbox.pack_start(self.label, True, True, padding = 4)
        alignment = Gtk.Alignment()
        alignment.set(1, 0.5, 0, 0)
        alignment.add(self.close_button)
        hbox.pack_start(alignment, False, False, 0)

        vbox = Gtk.VBox()
        vbox.pack_start(hbox, False, True, 0)
        self.preview_box = Gtk.Alignment()
        self.preview_box.set(0.5, 0.5, 0, 0)
        self.preview_box.set_padding(4, 2, 0, 0)
        self.preview = Gtk.Image()
        self.preview_box.add(self.preview)
        self.preview.show()
        vbox.pack_start(self.preview_box, True, True, 0)
        self.add(vbox)
        self.preview_box.set_no_show_all(True)
        vbox.show_all()
        
        self.show_all()
        self.update_show_state()

        self.drag_dest_set(0, [], 0)
        self.drag_entered = False

        # for preview...
        self.preview_w = 300
        self.preview_h = 200
        self.d = None
        self.drawable = None
        self.pixmap = None
        self.window = None

        #self.connect("clicked", self.on_clicked)
        self.close_button.connect("button-press-event", self.disable_click)
        self.close_button.connect("clicked", self.__on_close_button_clicked)
        self.close_button.connect("leave-notify-event",
                                  self.__on_close_button_leave)
        connect(self.globals, "show-close-button-changed",
                              self.__on_show_close_button_changed)
        connect(self.globals, "color-changed", self.__update_label)
        connect(self.globals, "preview-size-changed", self.update_preview)
        connect(self.globals, "window-title-width-changed",
                              self.__update_label)

    def clean_up(self):
        window = self.window_r()
        if self.deopacify_sid:
            GLib.source_remove(self.deopacify_sid)
            window.deopacify()
        if self.opacify_sid:
            GLib.source_remove(self.opacify_sid)
        if self.press_sid:
            GLib.source_remove(self.press_sid)
        self.close_button.destroy()

    def show(self):
        self.update_preview()
        CairoButton.show(self)

    def __on_show_close_button_changed(self, *args):
        if self.globals.settings["show_close_button"]:
            self.close_button.show()
        else:
            self.close_button.hide()
            self.label.queue_resize()

    #### Apperance
    def __update_label(self, arg=None):
        """Updates the style of the label according to window state."""
        window = self.window_r()
        text = None
        try:
            text = escape(str(window.wnck.get_name()))
            if window.wnck.is_minimized():
                color = self.globals.colors["color4"]
            else:
                color = self.globals.colors["color2"]
        except:
            color = "#FFFFFF"

        text = "<span foreground=\"" + color + "\">" + text + "</span>"
        self.label.set_text(text)
        self.label.set_use_markup(True)
        if self.globals.settings["preview"]:
            # The label should be 140px wide unless there are more room
            # because the preview takes up more.
            size = 140
        else:
            size = self.globals.settings["window_title_width"]
        self.label.set_size_request(size, -1)
        #self.size_request()

    def __make_minimized_icon(self, icon):
        pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True,
                                          8, icon.get_width(),
                                          icon.get_height())
        pixbuf.fill(0x00000000)
        minimized_icon = pixbuf.copy()
        icon.composite(pixbuf, 0, 0, pixbuf.get_width(),
                         pixbuf.get_height(), 0, 0, 1, 1,
                         GdkPixbuf.InterpType.BILINEAR, 190)
        pixbuf.saturate_and_pixelate(minimized_icon, 0.12, False)
        return minimized_icon

    def __update_icon(self):
        window = self.window_r()
        icon = window.wnck.get_mini_icon()
        if window.wnck.is_minimized():
            pixbuf = self.__make_minimized_icon(icon)
            self.icon_image.set_from_pixbuf(pixbuf)
            if self.globals.settings["preview"] and \
               (self.globals.get_compiz_version() < "0.9" or \
               not self.globals.settings["preview_minimized"]):
                   self.preview.set_from_pixbuf(window.wnck.get_icon())
        else:
            self.icon_image.set_from_pixbuf(icon)
            self.preview.clear()

    def minimized_changed(self):
        window = self.window_r()
        self.__update_label()
        self.__update_icon()
        self.area.set_minimized(window.wnck.is_minimized())

    def active_changed(self):
        window = self.window_r()
        self.area.set_active_window(window.is_active_window)
        self.__update_label()

    def icon_changed(self):
        self.__update_icon()

    def needs_attention_changed(self):
        window = self.window_r()
        self.area.set_needs_attention(window.wnck.needs_attention())
        self.__update_label()

    def name_changed(self):
        self.__update_label()

    def set_highlighted(self, highlighted):
        self.area.set_highlighted(highlighted)

    def update_show_state(self):
        window = self.window_r()
        if (self.globals.settings["show_only_current_desktop"] and \
           not window.on_current_desktop) or \
           (self.globals.settings["show_only_current_monitor"] and \
           window.monitor != self.group_r().monitor):
            self.hide()
        else:
            self.show()

    def __get_window_pixbuf(self, pixmap, to_w, to_h):
        geo = pixmap.get_geometry()
        di = pixmap.get_image(0, 0, geo.width, geo.height, X.ZPixmap, 0xffffffff)

        img = Image.frombytes('RGBA', (geo.width, geo.height), di.data, 'raw', 'BGRA')
        img_pixbuf = GdkPixbuf.Pixbuf.new_from_data(img.tobytes(), GdkPixbuf.Colorspace.RGB, True, 8, \
                                                    geo.width, geo.height,\
                                                    len(img.getbands()) * geo.width,\
                                                    None, None)

        pixbuf = img_pixbuf.scale_simple(to_w, to_h, GdkPixbuf.InterpType.BILINEAR)

        del di
        del img
        del img_pixbuf
        return pixbuf

    ####Preview
    def set_preview(self, is_visible):
        #from Xlib.display import Display
        window = self.window_r()
        if self.globals.settings["preview"] is False or \
           window.wnck.is_minimized():
            return

        if is_visible is False:
            #self.preview.set_from_pixbuf(None)
            self.preview.clear()
            return

        d = Display()
        pixmap = d.create_resource_object('pixmap', window.xid)

        pixbuf = self.__get_window_pixbuf(pixmap, self.preview_w, self.preview_h)
        if pixbuf is not None:
            self.preview.set_from_pixbuf(pixbuf)

        del pixbuf
        pixmap.free()
        del pixmap
        d.close()
        del d

    def update_preview(self, *args):
        window = self.window_r()
        group = self.group_r()
        width = window.wnck.get_geometry()[2]
        height = window.wnck.get_geometry()[3]
        ar = group.monitor_aspect_ratio
        size = self.globals.settings["preview_size"]
        if width*ar < size and height < size:
            pass
        elif float(width) / height > ar:
            height = int(round(size * ar * height / width))
            width = int(round(size * ar))
        else:
            width = int(round(float(size) * width / height))
            height = size
        self.preview.set_size_request(width, height)
        self.preview_w = width
        self.preview_h = height

        return width, height

    def set_show_preview(self, show_preview):
        if show_preview:
            self.preview_box.show()
        else:
            self.preview_box.hide()

    def get_preview_allocation(self):
        a = self.preview.get_allocation()
        self.area.set_preview_allocation(a)
        return a

    #### Events
    def do_enter_notify_event(self, event):
        # In compiz there is a enter and
        # a leave event before a press event.
        # Keep that in mind when coding this def!
        CairoButton.do_enter_notify_event(self, event)
        if self.pressed :
            return
        if self.globals.settings["opacify"]:
            self.opacify_sid = \
                GLib.timeout_add(100, self.__opacify)

    def do_leave_notify_event(self, event):
        # In compiz there is a enter and a leave
        # event before a press event.
        # Keep that in mind when coding this def!
        CairoButton.do_leave_notify_event(self, event)
        self.pressed = False
        if self.globals.settings["opacify"]:
            self.deopacify_sid = \
                GLib.timeout_add(200, self.__deopacify)

    def do_button_press_event(self,event):
        # In compiz there is a enter and a leave event before
        # a press event.
        # self.pressed is used to stop functions started with
        # gobject.timeout_add from self.__on_mouse_enter
        # or self.__on_mouse_leave.
        CairoButton.do_button_press_event(self, event)
        self.pressed = True
        self.press_sid = GLib.timeout_add(600, self.__set_pressed_false)

    def do_clicked(self, event):
        window = self.window_r()
        if self.globals.settings["opacify"]:
            window.deopacify()

        if not event.get_button()[1] in (1, 2, 3):
            return
        button = {1:"left", 2: "middle", 3: "right"}[event.get_button()[1]]
        if event.state & Gdk.ModifierType.SHIFT_MASK:
            mod = "shift_and_"
        else:
            mod = ""
        action_str = "windowbutton_%s%s_click_action"%(mod, button)
        action = self.globals.settings[action_str]
        window.action_function_dict[action](window, self, event)

        popup_close = "windowbutton_close_popup_on_%s%s_click"%(mod, button)
        if self.globals.settings[popup_close]:
            self.group_r().popup.hide()
        pass

    def __set_pressed_false(self):
        # Helper function for __on_press_event.
        self.pressed = False
        self.press_sid = None
        return False

    def do_scroll_event(self, event):
        window = self.window_r()
        if self.globals.settings["opacify"]:
            window.deopacify()
        if not event.direction in (gtk.gdk.SCROLL_UP, gtk.gdk.SCROLL_DOWN):
            return
        direction = {gtk.gdk.SCROLL_UP: "scroll_up",
                     gtk.gdk.SCROLL_DOWN: "scroll_down"}[event.direction]
        action = self.globals.settings["windowbutton_%s"%direction]
        window.action_function_dict[action](window, self, event)
        if self.globals.settings["windowbutton_close_popup_on_%s"%direction]:
            self.group_r().popup.hide()

    def __on_close_button_clicked(self, *args):
        window = self.window_r()
        if self.globals.settings["opacify"]:
            window.deopacify()
        window.action_close_window()

    def __on_close_button_leave(self, widget, event):
        if not self.pointer_is_inside():
            self.do_leave_notify_event(event)

    #### D'n'D
    def do_drag_motion(self, drag_context, x, y, t):
        if not self.drag_entered:
            self.group_r().popup.expose()
            self.drag_entered = True
            self.dnd_select_window = \
                GLib.timeout_add(600, self.window_r().action_select_window)
        drag_context.drag_status(gtk.gdk.ACTION_PRIVATE, t)
        return True

    def do_drag_leave(self, drag_context, t):
        self.drag_entered = False
        GLib.source_remove(self.dnd_select_window)
        self.group_r().popup.expose()
        self.group_r().popup.hide_if_not_hovered()

    #### Opacify
    def __opacify(self):
        window = self.window_r()
        if window.wnck.is_minimized():
            return False
        # if self.pressed is true, opacity_request is called by an
        # wrongly sent out enter_notification_event sent after a
        # press (because of a bug in compiz).
        if self.pressed:
            self.pressed = False
            return False
        # Check if mouse cursor still is over the window button.
        if self.pointer_is_inside():
            window.opacify()
            # Just for safety in case no leave-signal is sent
            self.deopacify_sid = \
                            GLib.timeout_add(500, self.__deopacify)
        return False

    def __deopacify(self):
        window = self.window_r()
        # Make sure that mouse cursor really has left the window button.
        b_m_x,b_m_y = self.get_pointer()
        b_r = self.get_allocation()
        if b_m_x >= 0 and b_m_x < b_r.width \
        and b_m_y >= 0 and b_m_y < b_r.height:
            return True
        # Wait before deopacifying in case a new windowbutton
        # should call opacify, to avoid flickering
        window.deopacify_sid = GLib.timeout_add(150, window.deopacify)
        return False

    #### Menu functions
    def show_menu(self, event):
        window = self.window_r()
        #Creates a popup menu
        menu = gtk.Menu()
        menu.connect("selection-done", self.__menu_closed)
        #(Un)Minimize
        minimize_item = None
        if window.wnck.get_actions() & WNCK_WINDOW_ACTION_MINIMIZE \
        and not window.wnck.is_minimized():
            minimize_item = gtk.MenuItem(_("_Minimize"))
        elif window.wnck.get_actions() & WNCK_WINDOW_ACTION_UNMINIMIZE \
        and window.wnck.is_minimized():
            minimize_item = gtk.MenuItem(_("Un_minimize"))
        if minimize_item:
            menu.append(minimize_item)
            minimize_item.connect("activate", window.action_minimize_window)
            minimize_item.show()
        # (Un)Maximize
        maximize_item = None
        if not window.wnck.is_maximized() \
        and window.wnck.get_actions() & WNCK_WINDOW_ACTION_MAXIMIZE:
            maximize_item = gtk.MenuItem(_("Ma_ximize"))
        elif window.wnck.is_maximized() \
        and window.wnck.get_actions() & WNCK_WINDOW_ACTION_UNMINIMIZE:
            maximize_item = gtk.MenuItem(_("Unma_ximize"))
        if maximize_item:
            menu.append(maximize_item)
            maximize_item.connect("activate", window.action_maximize_window)
            maximize_item.show()
        # Close
        close_item = gtk.MenuItem(_("_Close"))
        menu.append(close_item)
        close_item.connect("activate", window.action_close_window)
        close_item.show()
        menu.popup(None, None, None, event.button, event.time)
        self.globals.gtkmenu_showing = True

    def __menu_closed(self, menushell):
        self.globals.gtkmenu_showing = False
        self.group_r().popup.hide()
        menushell.destroy()
