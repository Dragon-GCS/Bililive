# Float window to display Bilibili DanMu 
# Written by Andy(2210132692) mainly and DragonZ

from __future__ import annotations

import argparse
import json
import sys
import tkinter as tk
from datetime import datetime
from enum import Enum
from threading import Thread
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

import cjkwrap  # type: ignore
from tornado.ioloop import IOLoop

from bililive.exception import RoomDisconnectException, RoomNotFoundException
from bililive.message import MessageType
from bililive.room import LiveRoom

T = TypeVar("T")

_register: Dict[str, str] = {}


def _bind(
    key: str,
) -> Callable[[Callable[[T, tk.Event[Any]], None]], Callable[[T, tk.Event[Any]], None]]:
    def decorator(
        func: Callable[[T, tk.Event[Any]], None]
    ) -> Callable[[T, tk.Event[Any]], None]:
        _register[key] = func.__name__
        return func

    return decorator


def _make_bind(tk: tk.Tk) -> None:
    for key, name in _register.items():
        tk.bind(key, tk.__getattribute__(name))


def _newText(contents: tk.Frame, config: Config) -> tk.Text:
    text = tk.Text(
        contents,
        width=config.width - 10,
        height=config.height,
        fg=config.font_color,
        bg=config.bg,
        font=config.font,
        borderwidth=0,
        #wrap="word",
        state="disabled",
    )
    text.bindtags(tuple(x for x in text.bindtags() if x != "Text"))
    return text


class Config:
    alpha: float = 0.6
    bg: str = "#000001"
    show_bg: str = "#080808"
    font_color: str = "#FFFFFF"
    width: int = 500
    height: int = 300
    font: Tuple[str, int] = ("微软雅黑", 16)
    numOfLines: int = 10
    charsOfLine: int = 46


class FloatWin(tk.Tk):
    _config: Config
    contents: tk.Frame
    texts: List[tk.Text] = []
    scrollBar: tk.Scrollbar

    alive: bool = True
    click_x: Optional[int] = None
    click_y: Optional[int] = None
    messages: List[str] = []
    cursor: int = -1
    cursor_lock = True

    @_bind("<MouseWheel>")
    def scroll(self, event: tk.Event[Any]) -> None:
        """滚轮滚动"""
        if event.delta < 0:
            self.cursor += 1
            if self.cursor >= len(self.messages):
                self.cursor = len(self.messages) - 1
                self.cursor_lock = True
        elif event.delta > 0:
            self.cursor_lock = False
            self.cursor -= 1 if self.cursor >= self._config.numOfLines else 0
        self.refresh()
        # self.text.yview("scroll", event.delta, "units")  # type: ignore

    @_bind("<Button-3>")
    def _quit(self, event: tk.Event[Any]) -> None:
        """右键退出"""
        self.alive = False
        self.quit()

    @_bind("<Button-1>")
    def click(self, event: tk.Event[Any]) -> None:
        """左键点击"""
        self.click_x = event.x
        self.click_y = event.y

    @_bind("<B1-Motion>")
    def move(self, event: tk.Event[Any]) -> None:
        """左键拖拽"""
        if not self.click_x or not self.click_y:
            return
        new_x = (event.x - self.click_x) + self.winfo_x()
        new_y = (event.y - self.click_y) + self.winfo_y()
        self._setPosition(new_x, new_y)
        print(f"move window to {new_x}, {new_y}")

    def __init__(self, config: Optional[Config] = None):
        super().__init__()
        self._config = config if config else Config()
        self._init_misc()
        self._init_widgets()
        _make_bind(self)

    def _init_misc(self) -> None:
        self.overrideredirect(True)  # remove border
        self.attributes("-alpha", self._config.alpha)  # backgroud transparency
        # self.attributes("-transparentcolor", self._config.bg)  # click through
        self.wm_attributes("-topmost", 1)  # Always on top
        self._setPosition(self.winfo_screenwidth() - self._config.width, 0)
        self.columnconfigure(0, weight=1)  # type: ignore
        self.rowconfigure(0, weight=1)  # type: ignore

    def _init_widgets(self) -> None:
        self.contents = tk.Frame(self)
        self.contents.grid(row=0, column=0, sticky=tk.NSEW)
        self.contents.columnconfigure(0, weight=1)  # type: ignore
        for i in range(self._config.numOfLines):
            self.contents.rowconfigure(i, weight=1)  # type: ignore
            text = _newText(self.contents, self._config)
            text.grid(row=i, column=0, sticky=tk.NSEW)
            self.texts.append(text)
        self.scrollBar = tk.Scrollbar(self, command=self._scrollTo)  # bind scroll bar
        self.scrollBar.grid(row=0, column=1, sticky=tk.NS)
        print(self.bindtags())
        self.scrollBar.bindtags(
            tuple(x for x in self.scrollBar.bindtags() if x not in self.bindtags())
        )
        # self.text["yscrollcommand"] = self.yscroll.set  # text scroll
        # self.text.grid(row=0, column=0, sticky=tk.NSEW)

    def _scrollTo(self, tag: Any, f: str, unit: Any = None) -> None:
        if tag == tk.MOVETO:
            self.cursor = round(float(f) * (len(self.messages) - 1))
            self.cursor_lock = self.cursor == len(self.messages) - 1
            self.refresh()
        print((tag, f, unit))

    def _setPosition(self, woffset: int, hoffset: int) -> None:
        self.geometry(
            "{width}x{height}+{woffset}+{hoffset}".format(
                width=self._config.width,
                height=self._config.height,
                woffset=woffset,
                hoffset=hoffset,
            )
        )

    def refresh(self) -> None:
        for text in self.texts:
            text["state"] = "normal"
            text.delete("1.0", "end")
        num_total = len(self.messages)
        num_fresh = min(num_total, self._config.numOfLines)
        start, stop = self.cursor + 1 - num_fresh, self.cursor + 1
        for text, msg in zip(self.texts[:num_fresh], self.messages[start:stop]):
            text.insert("end", msg)
            text["state"] = "disabled"
        self.scrollBar.set(  # type: ignore
            first=start / num_total, last=stop / num_total
        )

    def push(self, message: str) -> None:
        for s in cjkwrap.wrap(message, self._config.charsOfLine):
            self.messages.append(s)
        if self.cursor_lock:
            self.cursor = len(self.messages) - 1
            self.refresh()


room = LiveRoom()


class CoinType(str, Enum):
    银瓜子 = "silver"
    金瓜子 = "gold"


class GuardLevel(int, Enum):
    路人 = 0
    总督 = 1
    提督 = 2
    舰长 = 3


@room.on_message(MessageType.DANMU_MSG)
def danmu_handler(msg: bytes) -> None:
    """弹幕消息处理"""
    j = json.loads(msg)
    info = j["info"]

    text = info[1]
    uid = info[2][0]
    uname = info[2][1]
    ts = info[9]["ts"]
    dt = datetime.fromtimestamp(ts)
    assert win is not None
    win.push(f"[{dt.time()}] {uname}({uid}): {text}")
    print(f"[{dt.time()}] {uname}({uid}): {text}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="哔哩哔哩直播间弹幕检测工具")
    parser.add_argument("room_id", type=int, metavar="room_id", help="直播间房号")
    args = parser.parse_args()
    room_id = args.room_id

    try:
        # 获取直播间信息
        await room.update_info(room_id)
        print(room.info.title)

        # 连接直播间
        await room.connect()
    except RoomNotFoundException as e:
        print(f"直播间 {e.room_id} 不存在.")
        sys.exit(1)
    except RoomDisconnectException as e:
        print(f"直播间 {e.room_id} 已断开连接.")


win: Optional[FloatWin] = None


def start_tk() -> None:
    global win
    config = Config()
    win = FloatWin(config)
    win.mainloop()


if __name__ == "__main__":

    Thread(target=start_tk).start()
    while not win:
        pass
    try:
        IOLoop.current().run_sync(main)
    except KeyboardInterrupt:
        print("正在退出...")
