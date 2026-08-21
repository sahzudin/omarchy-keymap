import QtQuick
import Quickshell
import qs.Ui

// Optional launcher. The settings panel itself is a separate panel entry, so
// hiding this widget does not disable the plugin.
BarWidget {
  id: root
  moduleName: "io.github.sahzudin.keymap"

  readonly property bool opened: false
  readonly property bool popoutSwitchClosing: false

  function open() {
    Quickshell.execDetached(["omarchy-shell", "shell", "summon", moduleName, "{}"])
  }
  function close() {
    Quickshell.execDetached(["omarchy-shell", "shell", "hide", moduleName])
  }
  function toggle() {
    Quickshell.execDetached(["omarchy-shell", "shell", "toggle", moduleName, "{}"])
  }
  function closeForPopoutSwitch() { close() }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰌌"
    tooltipText: "Keyboard Shortcuts"
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.LeftButton) root.toggle()
    }
  }
}
