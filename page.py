# page.py

"""
This module contains the PageWindow class which is a window that you
can do simple drawings upon. and add Buttons and TextFields to.
"""


import wx
from wx.lib.docview import CommandProcessor, Command
import sys
import json
from runner import Runner
from uiViews import UiButton, UiTextField, UiPage

# ----------------------------------------------------------------------

class PageWindow(wx.Window):
    menuColours = { 100 : 'White',
                    101 : 'Yellow',
                    102 : 'Red',
                    103 : 'Green',
                    104 : 'Blue',
                    105 : 'Purple',
                    106 : 'Brown',
                    107 : 'Aquamarine',
                    108 : 'Forest Green',
                    109 : 'Light Blue',
                    110 : 'Goldenrod',
                    111 : 'Cyan',
                    112 : 'Orange',
                    113 : 'Black',
                    114 : 'Dark Grey',
                    115 : 'Light Grey',
                    }
    maxThickness = 16

    def __init__(self, parent, ID):
        wx.Window.__init__(self, parent, ID, style=wx.NO_FULL_REPAINT_ON_RESIZE)
        self.SetBackgroundColour("WHITE")
        self.listeners = []
        self.shapes = []
        self.designer = None
        self.command_processor = CommandProcessor()
        self.isEditing = False
        self.pos = wx.Point(0,0)
        self.isInDrawingMode = False
        self.isDrawing = False
        self.nextId = 1000
        self.thickness = 4
        self.SetColour("Black")
        self.runner = None
        # self.MakeMenu()

        self.uiViews = []
        self.uiPage = UiPage(self)
        self.uiViews.append(self.uiPage)
        self.timer = None

        self.selectedView = None

        self.InitBuffer()

        self.UpdateCursor()

        # hook some mouse events
        self.Bind(wx.EVT_LEFT_DOWN, self.OnMouseDown)
        self.Bind(wx.EVT_LEFT_UP, self.OnMouseUp)
        # if editing:
        #     self.Bind(wx.EVT_RIGHT_UP, self.OnMouseRightUp)
        self.Bind(wx.EVT_MOTION, self.OnMouseMove)

        # the view resize event and idle events for managing the buffer
        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_IDLE, self.OnIdle)

        # and the refresh event
        self.Bind(wx.EVT_PAINT, self.OnPaint)

        # When the window is destroyed, clean up resources.
        self.Bind(wx.EVT_WINDOW_DESTROY, self.Cleanup)

    def SetEditing(self, editing):
        self.isEditing = editing
        for ui in self.uiViews:
            ui.SetEditing(editing)
        if not editing:
            self.timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self.uiPage.OnIdle, self.timer)
            self.timer.Start(100)

    def UpdateCursor(self):
        self.SetCursor(wx.Cursor(wx.CURSOR_PENCIL if self.isInDrawingMode else wx.CURSOR_HAND))

    def SetDrawingMode(self, drawMode):
        self.isInDrawingMode = drawMode
        self.UpdateCursor()

    def ClearAll(self):
        self.SetLinesData([])
        self.SelectUIView(None)

        for ui in self.uiViews.copy():
            if ui.type != "page":
                self.uiViews.remove(ui)
                ui.DestroyView()
            else:
                for k,v in ui.GetHandlers().items():
                    ui.SetHandler(k,"")

    def GetData(self):
        data = {}
        data["shapes"] = self.GetShapesData()
        data["uiviews"] = self.GetUIViewsData()
        return data

    def LoadFromData(self, data):
        self.ClearAll()
        self.SetLinesData(data["shapes"])
        self.SetUIViewsData(data["uiviews"])

    def SetDesigner(self, designer):
        self.designer = designer

    def Cleanup(self, evt):
        if hasattr(self, "menu"):
            self.menu.Destroy()
            del self.menu
        if self.timer:
            self.timer.Stop()

    def InitBuffer(self):
        """Initialize the bitmap used for buffering the display."""
        size = self.GetClientSize()
        self.buffer = wx.Bitmap(max(1,size.width), max(1,size.height))
        dc = wx.BufferedDC(None, self.buffer)
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        self.DrawShapes(dc)
        self.reInitBuffer = False

    def SetColour(self, colour):
        """Set a new colour and make a matching pen"""
        self.colour = colour
        self.pen = wx.Pen(self.colour, self.thickness, wx.PENSTYLE_SOLID)
        self.Notify()

    def SetThickness(self, num):
        """Set a new line thickness and make a matching pen"""
        self.thickness = num
        self.pen = wx.Pen(self.colour, self.thickness, wx.PENSTYLE_SOLID)
        self.Notify()

    def AddUiViewOfType(self, viewType):
        if viewType == "button":
            command = AddUIViewCommand(True, 'Add Button', self, "button", self.nextId)
            self.command_processor.Submit(command)
        elif viewType == "textfield":
            command = AddUIViewCommand(True, 'Add TextField', self, "textfield", self.nextId)
            self.command_processor.Submit(command)
        self.SelectUIView(self.GetUIViewById(self.nextId))
        self.nextId += 1

    def AddUiViewFromData(self, data):
        uiView = None
        if data["type"] == "button":
            uiView = UiButton(self, self.nextId)
        elif data["type"] == "textfield":
            uiView = UiTextField(self, self.nextId)
        elif data["type"] == "page":
            uiView = self.uiPage
        self.nextId += 1
        self.uiViews.append(uiView)
        uiView.SetData(data)
        uiView.SetEditing(self.isEditing)

    def GetShapesData(self):
        return self.shapes[:]

    def SetLinesData(self, lines):
        self.shapes = lines[:]
        self.InitBuffer()
        self.Refresh()

    def GetUIViewsData(self):
        return [v.GetData() for v in self.uiViews]

    def SetUIViewsData(self, data):
        self.uiViews = []
        for v in data:
            self.AddUiViewFromData(v)

    def GetSelectedUIView(self):
        return self.selectedView

    def SelectUIView(self, view):
        if self.selectedView:
            self.selectedView.SetSelected(False)
        if view:
            view.SetSelected(True)
        self.selectedView = view
        if self.designer:
            self.designer.SetSelectedUIView(view)

    def UpdateSelectedUIView(self):
        if self.designer:
            self.designer.UpdateSelectedUIView()

    def GetNextAvailableName(self, base):
        names = map(lambda ui: ui.GetProperty("name"), self.uiViews)
        i = 1
        while True:
            name = base+str(i)
            if name not in names:
                return name
            i += 1

    def GetUIViewById(self, viewId):
        for ui in self.uiViews:
            if ui.view.GetId() == viewId:
                return ui
        return None

    def RemoveUIViewById(self, viewId):
        for ui in self.uiViews.copy():
            if ui.view.GetId() == viewId:
                self.uiViews.remove(ui)
                if self.selectedView == ui:
                    self.SelectUIView(None)

    # def MakeMenu(self):
    #     """Make a menu that can be popped up later"""
    #     menu = wx.Menu()
    #     for k in sorted(self.menuColours):
    #         text = self.menuColours[k]
    #         menu.Append(k, text, kind=wx.ITEM_CHECK)
    #     self.Bind(wx.EVT_MENU_RANGE, self.OnMenuSetColour, id=100, id2=200)
    #     self.Bind(wx.EVT_UPDATE_UI_RANGE, self.OnCheckMenuColours, id=100, id2=200)
    #     menu.Break()
    #
    #     for x in range(1, self.maxThickness+1):
    #         menu.Append(x, str(x), kind=wx.ITEM_CHECK)
    #
    #     self.Bind(wx.EVT_MENU_RANGE, self.OnMenuSetThickness, id=1, id2=self.maxThickness)
    #     self.Bind(wx.EVT_UPDATE_UI_RANGE, self.OnCheckMenuThickness, id=1, id2=self.maxThickness)
    #     self.menu = menu
    #
    #
    # # These two event handlers are called before the menu is displayed
    # # to determine which items should be checked.
    # def OnCheckMenuColours(self, event):
    #     text = self.menuColours[event.GetId()]
    #     if text == self.colour:
    #         event.Check(True)
    #         event.SetText(text.upper())
    #     else:
    #         event.Check(False)
    #         event.SetText(text)
    #
    # def OnCheckMenuThickness(self, event):
    #     if event.GetId() == self.thickness:
    #         event.Check(True)
    #     else:
    #         event.Check(False)
    #
    # def OnMouseRightUp(self, event):
    #     """called when the right mouse button is released, will popup the menu"""
    #     if self.isInDrawingMode:
    #         self.PopupMenu(self.menu)

    def OnMouseDown(self, event):
        """called when the left mouse button is pressed"""
        if self.isEditing:
            if self.isInDrawingMode:
                self.curLine = []
                self.pos = event.GetPosition()
                coords = (self.pos.x, self.pos.y)
                self.curLine.append(coords)
                self.isDrawing = True
                self.CaptureMouse()
            else:
                self.SelectUIView(None)
        else:
            event.Skip()

    def OnMouseUp(self, event):
        """called when the left mouse button is released"""
        if self.isEditing:
            if self.HasCapture():
                command = AddLineCommand(True, 'Add Line', self,
                                         ("pen", self.colour, self.thickness, self.curLine) )
                self.command_processor.Submit(command)
                self.curLine = []
                self.isDrawing = False
                self.ReleaseMouse()
        else:
            event.Skip()

    def OnMouseMove(self, event):
        """
        Called when the mouse is in motion.  If the left button is
        dragging then draw a line from the last event position to the
        current one.  Save the coordinants for redraws.
        """
        if self.isEditing:
            if self.isDrawing and event.Dragging() and event.LeftIsDown():
                dc = wx.BufferedDC(wx.ClientDC(self), self.buffer)
                dc.SetPen(self.pen)
                pos = event.GetPosition()
                coords = (pos.x, pos.y)
                self.curLine.append(coords)
                dc.DrawLine(*(self.pos.x, self.pos.y, pos.x, pos.y))
                self.pos = pos
        else:
            event.Skip()

    def OnSize(self, event):
        """
        Called when the window is resized.  We set a flag so the idle
        handler will resize the buffer.
        """
        self.reInitBuffer = True
        event.Skip()

    def OnIdle(self, event):
        """
        If the size was changed then resize the bitmap used for double
        buffering to match the window size.  We do it in Idle time so
        there is only one refresh after resizing is done, not lots while
        it is happening.
        """
        if self.reInitBuffer:
            self.InitBuffer()
            self.Refresh(False)
        event.Skip()

    def OnPaint(self, event):
        """
        Called when the window is exposed.
        """
        # Create a buffered paint DC.  It will create the real
        # wx.PaintDC and then blit the bitmap to it when dc is
        # deleted.  Since we don't need to draw anything else
        # here that's all there is to it.
        dc = wx.BufferedPaintDC(self, self.buffer)

    def DrawShapes(self, dc):
        """
        Redraws all the shapes that have been drawn already.
        """
        for type, colour, thickness, line in self.shapes:
            pen = wx.Pen(colour, thickness, wx.PENSTYLE_SOLID)
            dc.SetPen(pen)

            lastPos = None
            if type == "pen":
                for coords in line:
                    if lastPos:
                        dc.DrawLine(*(lastPos[0], lastPos[1], coords[0], coords[1]))
                    lastPos = coords

    # Event handlers for the popup menu, uses the event ID to determine
    # the colour or the thickness to set.
    def OnMenuSetColour(self, event):
        self.SetColour(self.menuColours[event.GetId()])

    def OnMenuSetThickness(self, event):
        self.SetThickness(event.GetId())

    def Undo(self):
        self.command_processor.Undo()
        self.InitBuffer()
        self.Refresh()

    def Redo(self):
        self.command_processor.Redo()
        self.InitBuffer()
        self.Refresh()

    # Observer pattern.  Listeners are registered and then notified
    # whenever doodle settings change.
    def AddListener(self, listener):
        self.listeners.append(listener)

    def Notify(self):
        for other in self.listeners:
            other.UpdateLine(self.colour, self.thickness)


class AddLineCommand(Command):
    parent = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.parent = args[2]
        self.line = args[3]

    def Do(self):
        self.parent.shapes.append(self.line)
        return True

    def Undo(self):
        if len(self.parent.shapes):
            self.parent.shapes.pop();
        return True


class AddUIViewCommand(Command):
    uiView = None

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.page = args[2]
        self.viewType = args[3]
        self.viewId = self.page.nextId

    def Do(self):
        if self.viewType == "button":
            self.uiView = UiButton(self.page, self.viewId)
        elif self.viewType == "textfield":
            self.uiView = UiTextField(self.page, self.viewId)

        if self.uiView:
            self.uiView.view.Center()
            self.page.uiViews.append(self.uiView)
            self.uiView.SetEditing(self.page.isEditing)
            return True
        return False

    def Undo(self):
        self.page.RemoveUIViewById(self.viewId)
        self.uiView.DestroyView()
        self.uiView = None
        return True