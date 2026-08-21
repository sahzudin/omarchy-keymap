.pragma library

function keyName(event) {
  var key = event.key

  if (key >= Qt.Key_A && key <= Qt.Key_Z)
    return String.fromCharCode(key)
  if (key >= Qt.Key_0 && key <= Qt.Key_9)
    return String.fromCharCode(key)
  if (key >= Qt.Key_F1 && key <= Qt.Key_F35)
    return "F" + String(key - Qt.Key_F1 + 1)

  var names = {}
  names[Qt.Key_Return] = "RETURN"
  names[Qt.Key_Enter] = "RETURN"
  names[Qt.Key_Tab] = "TAB"
  names[Qt.Key_Backtab] = "TAB"
  names[Qt.Key_Space] = "SPACE"
  names[Qt.Key_Backspace] = "BACKSPACE"
  names[Qt.Key_Delete] = "DELETE"
  names[Qt.Key_Insert] = "INSERT"
  names[Qt.Key_Home] = "HOME"
  names[Qt.Key_End] = "END"
  names[Qt.Key_PageUp] = "PAGEUP"
  names[Qt.Key_PageDown] = "PAGEDOWN"
  names[Qt.Key_Left] = "LEFT"
  names[Qt.Key_Right] = "RIGHT"
  names[Qt.Key_Up] = "UP"
  names[Qt.Key_Down] = "DOWN"
  names[Qt.Key_Print] = "PRINT"
  names[Qt.Key_Pause] = "PAUSE"
  names[Qt.Key_Menu] = "MENU"
  names[Qt.Key_Minus] = "MINUS"
  names[Qt.Key_Equal] = "EQUAL"
  names[Qt.Key_Comma] = "comma"
  names[Qt.Key_Period] = "PERIOD"
  names[Qt.Key_Slash] = "SLASH"
  names[Qt.Key_Backslash] = "BACKSLASH"
  names[Qt.Key_BracketLeft] = "BRACKETLEFT"
  names[Qt.Key_BracketRight] = "BRACKETRIGHT"
  names[Qt.Key_Semicolon] = "SEMICOLON"
  names[Qt.Key_Apostrophe] = "APOSTROPHE"
  names[Qt.Key_QuoteLeft] = "GRAVE"
  names[Qt.Key_MonBrightnessUp] = "XF86MONBRIGHTNESSUP"
  names[Qt.Key_MonBrightnessDown] = "XF86MONBRIGHTNESSDOWN"
  names[Qt.Key_KeyboardLightOnOff] = "XF86KBDLIGHTONOFF"
  names[Qt.Key_KeyboardBrightnessUp] = "XF86KBDBRIGHTNESSUP"
  names[Qt.Key_KeyboardBrightnessDown] = "XF86KBDBRIGHTNESSDOWN"
  names[Qt.Key_VolumeUp] = "XF86AUDIORAISEVOLUME"
  names[Qt.Key_VolumeDown] = "XF86AUDIOLOWERVOLUME"
  names[Qt.Key_VolumeMute] = "XF86AUDIOMUTE"
  names[Qt.Key_MicMute] = "XF86AUDIOMICMUTE"
  names[Qt.Key_MediaNext] = "XF86AUDIONEXT"
  names[Qt.Key_MediaPrevious] = "XF86AUDIOPREV"
  names[Qt.Key_MediaPlay] = "XF86AUDIOPLAY"
  names[Qt.Key_MediaTogglePlayPause] = "XF86AUDIOPLAY"
  names[Qt.Key_MediaPause] = "XF86AUDIOPAUSE"
  names[Qt.Key_MediaStop] = "XF86AUDIOSTOP"
  names[Qt.Key_Calculator] = "XF86CALCULATOR"
  names[Qt.Key_PowerOff] = "XF86POWEROFF"
  names[Qt.Key_TouchpadToggle] = "XF86TOUCHPADTOGGLE"
  names[Qt.Key_TouchpadOn] = "XF86TOUCHPADON"
  names[Qt.Key_TouchpadOff] = "XF86TOUCHPADOFF"

  return names[key] || ""
}

function isModifierKey(key) {
  return key === Qt.Key_Shift || key === Qt.Key_Control || key === Qt.Key_Alt
    || key === Qt.Key_Meta || key === Qt.Key_Super_L || key === Qt.Key_Super_R
    || key === Qt.Key_AltGr
}

function shortcutForEvent(event) {
  if (isModifierKey(event.key)) return ""
  var key = keyName(event)
  if (!key) return ""

  var parts = []
  if (event.modifiers & Qt.MetaModifier) parts.push("SUPER")
  if (event.modifiers & Qt.ShiftModifier) parts.push("SHIFT")
  if (event.modifiers & Qt.ControlModifier) parts.push("CTRL")
  if (event.modifiers & Qt.AltModifier) parts.push("ALT")
  parts.push(key)
  return parts.join(" + ")
}
