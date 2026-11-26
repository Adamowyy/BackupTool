#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kliknięcia w przyciski: CTk 6.0 gubi je bez wcześniejszego <Enter>."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk

import customtkinter as ctk

import app  # noqa: F401  (podmienia CTkButton._on_release)


class ClickTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = ctk.CTk()
        except tk.TclError:
            raise unittest.SkipTest("brak okna")
        cls.root.geometry("300x220+40+40")
        cls.root.attributes("-alpha", 0.0)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _button(self, hits, **kwargs):
        button = ctk.CTkButton(self.root, text="Test",
                               command=lambda: hits.append(1), **kwargs)
        button.pack()
        self.root.update()
        return button

    def test_click_without_hover_still_runs(self):
        hits = []
        button = self._button(hits)
        self.assertFalse(button._mouse_inside, "kursor nie był nad przyciskiem")
        button._canvas.event_generate("<ButtonRelease-1>", x=5, y=5, when="now")
        self.assertEqual(hits, [1])
        button.destroy()

    def test_hovered_click_runs_once(self):
        hits = []
        button = self._button(hits)
        button._on_enter()
        button._canvas.event_generate("<ButtonRelease-1>", x=5, y=5, when="now")
        self.assertEqual(hits, [1], "bez podwójnego wywołania")
        button.destroy()

    def test_disabled_button_ignores_click(self):
        hits = []
        button = self._button(hits, state="disabled")
        button._canvas.event_generate("<ButtonRelease-1>", x=5, y=5, when="now")
        self.assertEqual(hits, [])
        button.destroy()


if __name__ == "__main__":
    unittest.main()
