import json

from gettext import gettext as _
from subprocess import run, PIPE

from kitty import remote_control
from kitty.config import cached_values_for
from kitty.key_encoding import (
    BACKSPACE, CTRL, DOWN, ESCAPE, LEFT, RELEASE, RIGHT, TAB, UP, config_mod_map, enter_key
)

from kittens.tui.handler import Handler
from kittens.tui.line_edit import LineEdit
from kittens.tui.loop import Loop
from kittens.tui.operations import (
    clear_screen, cursor, set_line_wrapping, set_window_title, styled
)


class Search(Handler):
    def __init__(self, cached_values, window_id, error=''):
        self.cached_values = cached_values
        self.window_id = window_id
        self.error = error
        self.line_edit = LineEdit()
        last_search = cached_values.get('last_search', '')
        self.line_edit.add_text(last_search)
        self.text_marked = bool(last_search)
        self.mode = cached_values.get('mode', 'text')
        self.update_prompt()
        self.mark()

    def update_prompt(self):
        self.prompt = '~> ' if self.mode == 'regex' else '=> '

    def init_terminal_state(self):
        self.write(set_line_wrapping(False))
        self.write(set_window_title(_('Search')))

    def initialize(self):
        self.init_terminal_state()
        self.draw_screen()

    def draw_screen(self):
        self.write(clear_screen())
        if self.window_id:
            input_text = self.line_edit.current_input
            if self.text_marked:
                self.line_edit.current_input = styled(input_text, reverse=True)
            self.line_edit.write(self.write, self.prompt)
            self.line_edit.current_input = input_text
        if self.error:
            with cursor(self.write):
                self.print('')
                for l in self.error.split('\n'):
                    self.print(l)

    def refresh(self):
        self.draw_screen()
        self.mark()

    def switch_mode(self):
        if self.mode == 'regex':
            self.mode = 'text'
        else:
            self.mode = 'regex'
        self.cached_values['mode'] = self.mode
        self.update_prompt()

    def on_text(self, text, in_bracketed_paste):
        if self.text_marked:
            self.text_marked = False
            self.line_edit.clear()
        self.line_edit.on_text(text, in_bracketed_paste)
        self.refresh()

    def on_key(self, key_event):
        if self.text_marked and key_event.key not in [TAB, 'LEFT_CONTROL', 'RIGHT_CONTROL', 'LEFT_ALT', 'RIGHT_ALT', 'LEFT_SUPER', 'RIGHT_SUPER']:
            self.text_marked = False
            self.refresh()

        if self.line_edit.on_key(key_event):
            self.refresh()
            return

        if key_event.type is not RELEASE:
            if key_event.mods == CTRL and key_event.key == 'U':
                self.line_edit.clear()
                self.refresh()
            elif key_event.mods == CTRL and key_event.key == 'A':
                self.line_edit.home()
                self.refresh()
            elif key_event.mods == CTRL and key_event.key == 'E':
                self.line_edit.end()
                self.refresh()
            elif key_event.key is TAB:
                self.switch_mode()
                self.refresh()
            elif key_event.key is UP:
                remote_control.main(['', 'kitten', self.match_arg(), 'scroll_mark.py'])
            elif key_event.key is DOWN:
                remote_control.main(['', 'kitten', self.match_arg(), 'scroll_mark.py', 'next'])

        if key_event is enter_key:
            self.quit(0)
        elif key_event.type is RELEASE:
            if not key_event.mods:
                if key_event.key is ESCAPE:
                    self.quit(1)

    def on_interrupt(self):
        self.quit(1)

    def on_eot(self):
        self.quit(1)

    def on_resize(self, new_size):
        self.refresh()

    def match_arg(self):
        return f'--match=id:{self.window_id}'

    def mark(self):
        if not self.window_id:
            return
        text = self.line_edit.current_input
        if text:
            match_case = 'i' if text.islower() else ''
            match_type = match_case + self.mode
            remote_control.main(['', 'create-marker', self.match_arg(), match_type, '1', text])
        else:
            self.remove_mark()

    def remove_mark(self):
            remote_control.main(['', 'remove-marker', self.match_arg()])

    def quit(self, return_code):
        self.cached_values['last_search'] = self.line_edit.current_input
        self.remove_mark()
        if return_code:
            remote_control.main(['', 'scroll-window', self.match_arg(), 'end'])
        self.quit_loop(return_code)


def main(args):
    try:
        remote_control.main(['', 'resize-window', '--self', '--axis=vertical', '--increment', '-100'])
    except:
        pass

    window_id = None
    error = ''
    ls_output = run(['kitty', '@', 'ls'], stdout=PIPE)
    ls_json = json.loads(ls_output.stdout.decode())
    for os_window in ls_json:
        if os_window['is_focused']:
            for tab in os_window['tabs']:
                if tab['is_focused']:
                    for kitty_window in tab['windows']:
                        if not kitty_window['is_focused']:
                            window_id = kitty_window['id']
    if not window_id:
        error = 'Could not find window to search in'

    loop = Loop()
    with cached_values_for('search') as cached_values:
        handler = Search(cached_values, window_id, error)
        loop.loop(handler)
