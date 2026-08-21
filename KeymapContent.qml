import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons
import "ShortcutModel.js" as ShortcutModel

FocusScope {
  id: root

  signal closeRequested()

  readonly property string backendPath: {
    var url = String(Qt.resolvedUrl("scripts/keymap.py"))
    return url.indexOf("file://") === 0 ? url.substring(7) : url
  }
  property var bindings: []
  property bool barVisible: false
  property bool busy: false
  property string statusText: "Loading shortcuts…"
  property string recordingId: ""
  property bool searchRecording: false
  property string searchBeforeRecording: ""
  property string capturedSearchShortcut: ""
  property string capturedSearchBeforeRecording: ""
  property var pendingConflict: null
  property string pendingShortcut: ""
  property string pendingSourceId: ""
  property var pendingCaptureRequest: null
  property bool captureSubmapActive: false
  readonly property bool capturingShortcut: recordingId !== "" || searchRecording
    || pendingCaptureRequest !== null

  readonly property var filteredBindings: {
    var needle = searchField.text.trim().toLowerCase()
    if (!needle) return root.bindings
    var normalizedNeedle = root.normalizeShortcutSearch(needle)
    return root.bindings.filter(function(binding) {
      var rawShortcut = String(binding.shortcut || binding.defaultShortcut || "")
      var displayShortcut = String(binding.displayShortcut || binding.displayDefaultShortcut || "")
      if (root.capturedSearchShortcut !== "") {
        var captured = root.normalizeShortcutSearch(root.capturedSearchShortcut)
        return root.normalizeShortcutSearch(rawShortcut) === captured
          || root.normalizeShortcutSearch(displayShortcut) === captured
      }
      return String(binding.title || "").toLowerCase().indexOf(needle) !== -1
        || String(binding.details || "").toLowerCase().indexOf(needle) !== -1
        || rawShortcut.toLowerCase().indexOf(needle) !== -1
        || displayShortcut.toLowerCase().indexOf(needle) !== -1
        || root.normalizeShortcutSearch(rawShortcut).indexOf(normalizedNeedle) !== -1
        || root.normalizeShortcutSearch(displayShortcut).indexOf(normalizedNeedle) !== -1
    })
  }

  function normalizeShortcutSearch(value) {
    return String(value || "").trim().toLowerCase()
      .replace(/control/g, "ctrl")
      .replace(/meta/g, "super")
      .replace(/\s*\+\s*/g, "+")
      .replace(/\s+/g, " ")
  }

  function bindingTitle(identifier) {
    for (var index = 0; index < root.bindings.length; index++) {
      if (root.bindings[index].id === identifier)
        return String(root.bindings[index].title || "this action")
    }
    return "this action"
  }

  function shortcutConflict(identifier, shortcut) {
    var wanted = root.normalizeShortcutSearch(shortcut)
    for (var index = 0; index < root.bindings.length; index++) {
      var binding = root.bindings[index]
      if (binding.id === identifier || binding.disabled) continue
      var raw = root.normalizeShortcutSearch(binding.shortcut || "")
      var displayed = root.normalizeShortcutSearch(binding.displayShortcut || "")
      if (raw === wanted || displayed === wanted) return binding
    }
    return null
  }

  function takeFocus() {
    searchField.forceActiveFocus()
  }

  function refresh() {
    if (listProcess.running) return
    listProcess.command = ["python3", root.backendPath, "list"]
    listProcess.running = true
  }

  function beginRecording(binding) {
    if (root.busy || !binding.supported) return
    root.pendingConflict = null
    root.pendingShortcut = ""
    root.pendingSourceId = ""
    root.startCapture({ mode: "edit", binding: binding })
  }

  function beginSearchRecording() {
    if (root.busy || root.recordingId !== "") return
    root.startCapture({
      mode: "search",
      previousSearch: searchField.text,
      previousCapturedSearch: root.capturedSearchShortcut
    })
  }

  function startCapture(request) {
    if (captureStartProcess.running || captureStopProcess.running
        || root.pendingCaptureRequest !== null) return
    root.pendingCaptureRequest = request
    root.statusText = "Preparing shortcut capture…"
    captureStartProcess.command = [
      "hyprctl", "dispatch", 'hl.dsp.submap("omarchy-keymap-capture")'
    ]
    captureStartProcess.running = true
  }

  function onCaptureStarted(exitCode) {
    var request = root.pendingCaptureRequest
    root.pendingCaptureRequest = null
    if (exitCode !== 0) {
      var message = String(captureStartError.text || "").trim()
      root.statusText = message || "Could not suspend Hyprland shortcuts."
      searchField.forceActiveFocus()
      return
    }
    root.captureSubmapActive = true
    if (request === null) {
      root.stopCaptureSubmap()
      return
    }
    if (request.mode === "search") {
      root.searchBeforeRecording = request.previousSearch || ""
      root.capturedSearchBeforeRecording = request.previousCapturedSearch || ""
      root.capturedSearchShortcut = ""
      root.searchRecording = true
      searchField.text = ""
      root.statusText = "Press a shortcut to search · Esc cancels"
    } else {
      root.recordingId = request.binding.id
      root.statusText = "Press the new shortcut · Esc cancels"
    }
    root.forceActiveFocus()
  }

  function stopCaptureSubmap() {
    if (!root.captureSubmapActive) return
    root.captureSubmapActive = false
    if (!captureStopProcess.running) {
      captureStopProcess.command = ["hyprctl", "dispatch", 'hl.dsp.submap("reset")']
      captureStopProcess.running = true
    }
  }

  function cancelCapture() {
    root.pendingCaptureRequest = null
    if (root.searchRecording) {
      root.searchRecording = false
      searchField.text = root.searchBeforeRecording
      root.capturedSearchShortcut = root.capturedSearchBeforeRecording
      root.searchBeforeRecording = ""
      root.capturedSearchBeforeRecording = ""
    }
    root.recordingId = ""
    root.stopCaptureSubmap()
  }

  function clearSearch() {
    root.searchRecording = false
    root.searchBeforeRecording = ""
    root.capturedSearchShortcut = ""
    root.capturedSearchBeforeRecording = ""
    searchField.clear()
    root.statusText = root.bindings.length + " shortcut groups"
    searchField.forceActiveFocus()
  }

  function runChange(arguments, label) {
    if (root.busy) return
    root.busy = true
    root.statusText = label
    changeProcess.command = ["python3", root.backendPath].concat(arguments)
    changeProcess.running = true
  }

  function setShortcut(identifier, shortcut, replaceExisting) {
    if (!replaceExisting) {
      var conflict = root.shortcutConflict(identifier, shortcut)
      if (conflict !== null) {
        root.pendingSourceId = identifier
        root.pendingShortcut = shortcut
        root.pendingConflict = conflict
        root.statusText = shortcut + " is currently assigned to " + conflict.title + "."
        return
      }
    }
    root.pendingSourceId = identifier
    root.pendingShortcut = shortcut
    var args = ["set", identifier, shortcut]
    if (replaceExisting) args.push("--replace")
    root.runChange(args, "Applying " + shortcut + "…")
  }

  function parseOutput(raw) {
    try { return JSON.parse(String(raw || "").trim()) }
    catch (error) { return { ok: false, error: "The backend returned invalid data." } }
  }

  function onListResult(raw) {
    var data = root.parseOutput(raw)
    if (!data.ok) {
      root.statusText = data.error || "Could not load shortcuts."
      return
    }
    root.bindings = Array.isArray(data.bindings) ? data.bindings : []
    root.barVisible = data.barVisible === true
    root.statusText = root.bindings.length + " shortcut groups"
  }

  function onChangeResult(raw) {
    root.busy = false
    var data = root.parseOutput(raw)
    if (data.ok) {
      root.pendingConflict = null
      root.pendingShortcut = ""
      root.pendingSourceId = ""
      root.statusText = "Applied"
      root.refresh()
      return
    }
    if (data.conflict) {
      root.pendingConflict = data.conflict
      root.statusText = data.error || "That shortcut is already in use."
    } else {
      root.statusText = data.error || "Could not apply the change."
    }
  }

  function onBarResult(raw) {
    root.busy = false
    var data = root.parseOutput(raw)
    if (data.ok) {
      root.barVisible = data.barVisible === true
      root.statusText = root.barVisible ? "Bar launcher shown" : "Bar launcher hidden"
    } else {
      root.statusText = data.error || "Could not update the bar."
    }
  }

  Keys.priority: Keys.BeforeItem
  Keys.onPressed: function(event) {
    if (root.searchRecording) {
      if (event.key === Qt.Key_Escape) {
        root.stopCaptureSubmap()
        root.searchRecording = false
        searchField.text = root.searchBeforeRecording
        root.capturedSearchShortcut = root.capturedSearchBeforeRecording
        root.searchBeforeRecording = ""
        root.capturedSearchBeforeRecording = ""
        root.statusText = root.bindings.length + " shortcut groups"
        searchField.forceActiveFocus()
        event.accepted = true
        return
      }
      if (!event.isAutoRepeat) {
        var searchShortcut = ShortcutModel.shortcutForEvent(event)
        if (searchShortcut !== "") {
          root.stopCaptureSubmap()
          root.searchRecording = false
          root.searchBeforeRecording = ""
          root.capturedSearchBeforeRecording = ""
          root.capturedSearchShortcut = searchShortcut
          searchField.text = searchShortcut
          root.statusText = root.filteredBindings.length + " matching shortcut groups"
          searchField.forceActiveFocus()
        }
      }
      event.accepted = true
      return
    }
    if (root.recordingId !== "") {
      if (event.key === Qt.Key_Escape) {
        root.stopCaptureSubmap()
        root.recordingId = ""
        root.statusText = "Shortcut capture cancelled"
        event.accepted = true
        return
      }
      if (event.isAutoRepeat) {
        event.accepted = true
        return
      }
      var shortcut = ShortcutModel.shortcutForEvent(event)
      if (shortcut !== "") {
        var identifier = root.recordingId
        root.stopCaptureSubmap()
        root.recordingId = ""
        root.setShortcut(identifier, shortcut, false)
        event.accepted = true
      }
      return
    }
    if (event.key === Qt.Key_Escape) {
      if (searchField.text !== "")
        root.clearSearch()
      else
        root.closeRequested()
      event.accepted = true
    }
  }

  Component.onCompleted: root.refresh()

  Process {
    id: listProcess
    command: []
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.onListResult(text)
    }
  }

  Process {
    id: changeProcess
    command: []
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.onChangeResult(text)
    }
  }

  Process {
    id: barProcess
    command: []
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.onBarResult(text)
    }
  }

  Process {
    id: captureStartProcess
    command: []
    stderr: StdioCollector {
      id: captureStartError
      waitForEnd: true
    }
    onExited: function(exitCode) { root.onCaptureStarted(exitCode) }
  }

  Process {
    id: captureStopProcess
    command: []
  }

  Column {
    anchors.fill: parent
    spacing: Style.space(10)

    Item {
      width: parent.width
      height: Math.max(headerIcon.implicitHeight, headerLabels.implicitHeight)

      Text {
        id: headerIcon
        text: "󰌌"
        color: Color.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.display
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
      }

      Column {
        id: headerLabels
        anchors.left: headerIcon.right
        anchors.leftMargin: Style.space(12)
        anchors.right: barButton.left
        anchors.rightMargin: Style.space(12)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(2)

        Text {
          text: "Keyboard Shortcuts"
          color: Color.foreground
          font.family: Style.font.family
          font.pixelSize: Style.font.title
          font.bold: true
        }
        Text {
          text: "Omarchy and Hyprland · changes apply immediately"
          color: Qt.darker(Color.foreground, 1.4)
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
        }
      }

      Button {
        id: barButton
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: root.barVisible ? "Hide bar icon" : "Show bar icon"
        bordered: true
        enabled: !root.busy
        onClicked: {
          root.busy = true
          root.statusText = root.barVisible ? "Hiding bar launcher…" : "Showing bar launcher…"
          barProcess.command = ["python3", root.backendPath, "set-bar", root.barVisible ? "false" : "true"]
          barProcess.running = true
        }
      }
    }

    Row {
      width: parent.width
      spacing: Style.space(8)

      TextField {
        id: searchField
        width: parent.width - searchShortcutButton.width - parent.spacing
          - (clearSearchButton.visible ? clearSearchButton.width + parent.spacing : 0)
        placeholderText: root.searchRecording ? "Press a shortcut…" : "Search actions or shortcuts…"
        foreground: Color.foreground
        enabled: !root.searchRecording
        onAccepted: root.forceActiveFocus()
        onTextEdited: root.capturedSearchShortcut = ""
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
          if (event.key !== Qt.Key_Escape || root.searchRecording) return
          if (searchField.text !== "")
            root.clearSearch()
          else
            root.closeRequested()
          event.accepted = true
        }
      }

      Button {
        id: clearSearchButton
        text: "Clear"
        bordered: true
        focusable: true
        visible: searchField.text !== "" && !root.searchRecording
        enabled: !root.busy
        onClicked: root.clearSearch()
      }

      Button {
        id: searchShortcutButton
        text: root.searchRecording ? "Press keys…" : "Press shortcut"
        bordered: true
        focusable: true
        enabled: !root.busy && root.recordingId === ""
          && !captureStartProcess.running && !captureStopProcess.running
        onClicked: {
          if (root.searchRecording) {
            root.cancelCapture()
            root.statusText = root.bindings.length + " shortcut groups"
            searchField.forceActiveFocus()
          } else {
            Qt.callLater(root.beginSearchRecording)
          }
        }
      }
    }

    BorderSurface {
      width: parent.width
      height: visible ? conflictColumn.implicitHeight + Style.space(16) : 0
      visible: root.pendingConflict !== null
      color: Style.hoverFillFor(Color.urgent, Color.urgent, Color.urgent)
      borderSpec: Border.controlSpec("focus", Color.urgent, Color.urgent)
      radius: Style.cornerRadius

      Column {
        id: conflictColumn
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.margins: Style.space(8)
        spacing: Style.space(6)

        Row {
          width: parent.width
          spacing: Style.space(8)

          Text {
            text: "⚠"
            color: Color.urgent
            font.family: Style.font.family
            font.pixelSize: Style.font.title
          }

          Text {
            text: "Shortcut conflict"
            color: Color.urgent
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            font.bold: true
          }
        }
        Text {
          width: parent.width
          text: root.pendingConflict === null ? "" :
            ("\u201c" + root.pendingShortcut + "\u201d is already assigned to \u201c"
              + String(root.pendingConflict.title || "another action") + "\u201d.")
          color: Color.foreground
          font.family: Style.font.family
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.WordWrap
        }
        Text {
          width: parent.width
          text: root.pendingConflict === null ? "" :
            ("Reassigning it to \u201c" + root.bindingTitle(root.pendingSourceId)
              + "\u201d will disable the shortcut for \u201c"
              + String(root.pendingConflict.title || "the existing action") + "\u201d.")
          color: Qt.darker(Color.foreground, 1.3)
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }
        Row {
          spacing: Style.space(8)
          Button {
            text: "Reassign shortcut"
            bordered: true
            foreground: Color.urgent
            accent: Color.urgent
            focusable: true
            onClicked: root.setShortcut(root.pendingSourceId, root.pendingShortcut, true)
          }
          Button {
            text: "Keep existing"
            bordered: true
            focusable: true
            onClicked: {
              root.pendingConflict = null
              root.pendingShortcut = ""
              root.pendingSourceId = ""
              root.statusText = root.bindings.length + " shortcut groups"
            }
          }
        }
      }
    }

    ScrollView {
      id: listView
      width: parent.width
      height: Math.max(0, parent.height - y - footer.height - parent.spacing)
      clip: true
      ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
      ScrollBar.vertical.policy: shortcutColumn.implicitHeight > height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff

      Column {
        id: shortcutColumn
        width: listView.availableWidth
        spacing: 0

        Repeater {
          model: root.filteredBindings

          Item {
            id: shortcutRow
            required property var modelData
            width: shortcutColumn.width
            height: Style.space(62)

            Rectangle {
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.bottom: parent.bottom
              height: Math.max(1, Style.normalBorderWidth)
              color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.12)
            }

            Column {
              anchors.left: parent.left
              anchors.right: actionRow.left
              anchors.rightMargin: Style.space(12)
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(2)

              Text {
                width: parent.width
                text: shortcutRow.modelData.title
                color: Color.foreground
                font.family: Style.font.family
                font.pixelSize: Style.font.body
                font.bold: shortcutRow.modelData.overridden
                elide: Text.ElideRight
              }
              Text {
                width: parent.width
                visible: text !== ""
                text: shortcutRow.modelData.subtitle || ""
                color: Qt.darker(Color.foreground, 1.45)
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                elide: Text.ElideRight
              }
            }

            Row {
              id: actionRow
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(6)

              Button {
                text: shortcutRow.modelData.disabled
                  ? "Disabled"
                  : (root.recordingId === shortcutRow.modelData.id
                    ? "Press keys…"
                    : (shortcutRow.modelData.displayShortcut || shortcutRow.modelData.shortcut))
                bordered: true
                enabled: shortcutRow.modelData.supported && !root.busy
                onClicked: {
                  root.pendingConflict = null
                  root.pendingShortcut = ""
                  root.beginRecording(shortcutRow.modelData)
                }
              }
              Button {
                visible: shortcutRow.modelData.supported && !shortcutRow.modelData.disabled
                text: "Disable"
                enabled: !root.busy
                onClicked: root.runChange(["disable", shortcutRow.modelData.id], "Disabling shortcut…")
              }
              Button {
                visible: shortcutRow.modelData.overridden
                text: "Reset"
                enabled: !root.busy
                onClicked: root.runChange(["reset", shortcutRow.modelData.id], "Restoring default…")
              }
            }
          }
        }
      }
    }

    Item {
      id: footer
      width: parent.width
      height: Math.max(statusLabel.implicitHeight, restoreAllButton.implicitHeight)

      Text {
        id: statusLabel
        anchors.left: parent.left
        anchors.right: restoreAllButton.left
        anchors.rightMargin: Style.space(12)
        anchors.verticalCenter: parent.verticalCenter
        text: root.statusText
        color: Qt.darker(Color.foreground, 1.35)
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        elide: Text.ElideRight
      }

      Button {
        id: restoreAllButton
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: "Restore all defaults"
        bordered: true
        enabled: !root.busy
        onClicked: root.runChange(["reset-all"], "Restoring all defaults…")
      }
    }
  }
}
