"""
# Copyright (C) 2009 ST8 <st8@q3f.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# For questions regarding this module contact
# ST8 <st8@q3f.org>

Python version for Live 8.0.1
    2.5.1 (r251:54863, Mar 31 2009, 16:56:21) [MSC v.1500 32 bit (Intel)]
    Presumably ableton moved to python 2.5 to stop decompyling of the APC40 module

"""

import Live
import RemixNet
import time
import re
#import os
from Logger import Logger

class MonomeButton:
    
    def __init__(self, matrix, x, y, callback):
        self.matrix = matrix
        self.x = x
        self.y = y
        self.callback = callback
        
    def process(self, x, y, v):
        if self.x == x and self.y == y:
            self.matrix.set_led(x, y, v)
            if v == 1:
                self.callback()
                return True
        return False
        
        
class ClipSlot:
    
    def __init__(self, matrix, x, y):
        self.matrix = matrix
        self.x = x
        self.y = y
        self.slot = None
        self.blink = False
        self.blink_slow = False
        
    def update(self):
        self.blink = not self.blink
        if self.blink:
            self.blink_slow = not self.blink_slow
        self.slot = None
        ax = self.x
        ay = self.y + self.matrix.scene_ofs
        if ay >= self.matrix.scene_count:
            return
        if ax >= len(self.matrix.song().scenes[ay].clip_slots):
            return
        self.slot = self.matrix.song().scenes[ay].clip_slots[ax]
        
    def press(self):
        if self.slot:
            self.slot.fire()
            self.matrix.playing_clips[self.x] = self.slot
            
    def has_clip(self):
        if self.slot:
            return self.slot.has_clip
        return False
        
    def is_triggered(self):
        if self.has_clip():
            return self.slot.clip.is_triggered

    def is_playing(self):
        if self.has_clip():
            return self.slot.clip.is_playing

    def is_led(self):
        if self.has_clip():
            if self.is_triggered():
                return self.blink
            if self.is_playing():
                return self.blink_slow
            return True
        return False
        
        
    
            

class MonomeMatrix:
    __module__ = __name__
    __doc__ = "Monome Clip Launcher"
    
    # Enable Logging
    _LOG = 0
    
    # Some variables
    prefix = "/ableton"
    
    width  = 8
    height = 8
        
    name = "MonomeMatrix"

    def __init__(self, app):
        self.app = app
   
        self.logger = self._LOG and Logger() or 0
        self.log("Logging Enabled")
        
        self.app.show_message("MonomeMatrix - Initializing")
        
        # Register buttons
        self.buttons = []
        self.register_button(0, self.height - 1, self.scroll_up_press)
        self.register_button(1, self.height - 1, self.scroll_down_press)
        self.register_button(6, self.height - 1, self.play_press)
        self.register_button(7, self.height - 1, self.stop_press)
        self.register_button(7, self.height - 2, self.stop_all_press)

        # Create OSC server
        self.oscServer = RemixNet.OSCServer('localhost', 8080, None, 8000)
        self.oscServer.sendOSC('/sys/prefix', self.prefix)
        self.oscServer.callbackManager.add(self.button_press, self.prefix + "/press")
        
        # Define variables
        self.scene_count = self.get_scene_count()
        self.scene_ofs = self.get_scene_ofs()
        self.last_ticks = 0
        
        # Build clip slot matrix
        self.clips = []
        for y in range(0, self.height - 2):
            row = []
            for x in range(0, self.width - 1):
                row.append(ClipSlot(self, x, y))
            self.clips.append(row)
        self.playing_clips = []
        for x in range(0, self.width - 1):
            self.playing_clips.append(None)
        self.update_clips()
        
        # Register global listeners
        self.song().add_scenes_listener(self.scenes_changed)
        self.song().add_tracks_listener(self.tracks_changed)
        self.song().view.add_selected_scene_listener(self.selected_scene_changed)
        self.song().add_current_song_time_listener(self.current_song_time_changed)
        
        # Zero leds
        for i in range(self.width):
            self.oscServer.sendOSC(self.prefix + "/led_col", (i, 0))
            
            
    # Button handling --------------------------------------------------------

    
    def button_press(self, msg):
        """ Called when a key was pressed on the monome. """
        
        x = msg[2]
        y = msg[3]
        v = msg[4]
        
        # General buttons
        for button in self.buttons:
            if button.process(x, y, v):
                return
                
        # Start clip buttons
        if x < self.width - 1 and y < self.height - 2 and v == 1:
            self.clips[y][x].press()
            
        # Start scene buttons
        if x == self.width - 1 and y < self.height - 2 and v == 0:
            old_scene_ofs = self.scene_ofs
            index = self.scene_ofs + y
            if index < self.scene_count:
                self.song().scenes[index].fire()
                self.song().view.selected_scene = self.song().scenes[old_scene_ofs]
                
        # Stop clip buttons
        if x < self.width - 1 and y == self.height - 2 and v == 0:
            if self.playing_clips[x]:
                self.playing_clips[x].stop()
                self.playing_clips[x] = None

    def register_button(self, x, y, callback):
        """ Registers a button. """
        
        self.buttons.append(MonomeButton(self, x, y, callback))

        
    # LED handling -----------------------------------------------------------


    def set_led(self, x, y, v):
        self.oscServer.sendOSC(self.prefix + "/led", (x, y, v))

        
    # Global listener handlers -----------------------------------------------
    
    
    def scenes_changed(self, x):
        self.scene_count = self.get_scene_count()
        self.update_clips()
        
    def tracks_changed(self):
        self.update_clips()
        
    def selected_scene_changed(self):
        self.scene_ofs = self.get_scene_ofs()
        self.log("scene ofs = %d" % (self.scene_ofs))
        
    def current_song_time_changed(self):
        if not self.song().is_playing:
            self.set_led(self.width - 1, self.height - 1, 0)
            return
        ticks = self.song().get_current_beats_song_time().sub_division
        if ticks == self.last_ticks:
            return
        if ticks == 1:
            self.set_led(self.width - 1, self.height - 1, 1)
        else:
            self.set_led(self.width - 1, self.height - 1, 0)
        self.last_ticks = ticks
        
        
    # Button handlers --------------------------------------------------------
        
        
    def scroll_up_press(self):
        if self.scene_ofs <= 0:
            return
        self.scene_ofs -= 1
        self.song().view.selected_scene = self.song().scenes[self.scene_ofs]
    
    def scroll_down_press(self):
        if self.scene_ofs >= self.scene_count - 1:
            return
        self.scene_ofs += 1
        self.song().view.selected_scene = self.song().scenes[self.scene_ofs]

    def play_press(self):
        self.song().start_playing()
        
    def stop_press(self):
        self.song().stop_playing()
        
    def stop_all_press(self):
        self.song().stop_all_clips()
        
        
    # Clip handling ----------------------------------------------------------
    
    
    def update_clips(self):
        for row in self.clips:
            for slot in row:
                slot.update()
        
        
    # Utilities --------------------------------------------------------------

        
    def get_scene_count(self):
        return len(self.song().scenes)
        
    def get_scene_ofs(self):
        return list(self.song().scenes).index(self.song().view.selected_scene)










    
######################################################################

    # Ableton Methods
    def disconnect(self):
        self.oscServer.shutdown()
        
        self.song().remove_scenes_listener(self.scenes_changed)
        self.song().remove_tracks_listener(self.tracks_changed)
        self.song().view.remove_selected_scene_listener(self.selected_scene_changed)
        self.song().remove_current_song_time_listener(self.current_song_time_changed)

    def connect_script_instances(self, instanciated_scripts):
        return

    def is_extension(self):
        return False

    def request_rebuild_midi_map(self):
        return

    def build_midi_map(self, midi_map_handle):
        self.log("build midi map")
        pass
        
	def send_midi(self, midi_bytes):
		self.app.send_midi(midi_bytes)

    def receive_midi(self, midi_bytes):        
        self.log(str(midi_bytes))
        
    def can_lock_to_devices(self):
        return False

    def suggest_input_port(self):
        return 'Midi Yoke NT: 1'

    def suggest_output_port(self):
        return 'Midi Yoke NT: 3'
        
    def suggest_map_mode(self, cc_no, channel):
        return Live.MidiMap.MapMode.absolute

    def __handle_display_switch_ids(self, switch_id, value):
        pass        

######################################################################

    # Ableton Methods
    def refresh_state(self):
        pass
        
    def update_display(self):
        self.update_clips()
        
        for y in range(0, self.height - 2):
            row = 0
            for x in range(0, self.width - 1):
                if self.clips[y][x].is_led():
                    row |= 1 << x
            self.oscServer.sendOSC(self.prefix + "/led_row", (y, row))
            
            
        if self.oscServer:
            try:
                self.oscServer.processIncomingUDP()
            except:
                pass
        

    def inspector(self):
        """
        Dumps three levels of functions and classes from the Live object
        """
        
        meh = open("c:\\live8.txt", "a")
        base = "Live"
        for fn in dir(eval(base)):
            if not re.search('^_', fn):
                meh.write(base + "." + fn + "\n");
                meh.write(str(dir(eval(base + "." + fn))) + "\n");    
                for sf in dir(eval(base + "." + fn)):
                    if not re.search('^_', sf):
                        meh.write(base + "." + fn + "." + sf + "\n");
                        meh.write(str(dir(eval(base + "." + fn + "." + sf))) + "\n");

                        for ssf in dir(eval(base + "." + fn + "." + sf)):
                            if not re.search('^_', ssf):
                                meh.write(base + "." + fn + "." + sf + "." + ssf + "\n");
                                meh.write(str(dir(eval(base + "." + fn + "." + sf + "." + ssf))) + "\n");
                
                meh.write("\n\n");
                    
        meh.close();
    
######################################################################

    # Useful Methods
    def log(self, msg):
        if self._LOG == 1:
            self.logger.log(self.name + ": " + msg)    
    
    def song(self):
        return self.app.song()

    def handle(self):
        return self.app.handle()

