#!/usr/bin/python
# stackManager.py

"""
This module contains the StackManager class which manages painting, editing, and
interacting with the stack.
This class is very central to CardStock, and right now, probably contains a bit more than it should.  :)
"""


import wx
from wx.lib.docview import CommandProcessor
import json
from tools import *
from commands import *
import generator
import findEngineDesigner
from stackModel import StackModel
from uiCard import UiCard, CardModel
from uiButton import UiButton
from uiTextField import UiTextField
from uiTextLabel import UiTextLabel
from uiImage import UiImage
from uiShape import UiShape
from uiGroup import UiGroup, GroupModel


# ----------------------------------------------------------------------

class StackManager(object):
    def __init__(self, parentView):
        self.view = wx.Window(parentView, style=wx.WANTS_CHARS)
        self.listeners = []
        self.designer = None
        self.isEditing = False  # Is in Editing mode (running from the designer), as opposed to just the viewer
        self.command_processor = CommandProcessor()
        self.noIdling = False
        self.timer = None
        self.tool = None
        self.globalCursor = None
        self.lastMousePos = wx.Point(0,0)
        self.lastFocusedTextField = None
        self.lastMouseMovedUiView = None
        self.isDoubleClick = False
        self.inlineEditingView = None
        self.runner = None
        self.filename = None

        self.stackModel = StackModel(self)
        self.stackModel.AppendCardModel(CardModel(self))

        self.selectedViews = []
        self.uiViews = []
        self.cardIndex = None
        self.uiCard = UiCard(None, self, self.stackModel.childModels[0])
        self.LoadCardAtIndex(0)

        self.uiCard.model.SetDirty(False)
        self.command_processor.ClearCommands()

        if wx.Platform != '__WXMAC__':
            # Skip double-buffering on Mac, as it's much faster without it, and looks great
            self.buffer = None
            self.view.Bind(wx.EVT_SIZE, self.OnResize)

        self.view.Bind(wx.EVT_PAINT, self.OnPaint)
        self.view.Bind(wx.EVT_LEAVE_WINDOW, self.OnMouseExit)
        self.view.Bind(wx.EVT_WINDOW_DESTROY, self.Cleanup)

    def Cleanup(self, event):
        """When the window is destroyed, clean up resources."""
        if event.GetEventObject() == self.view:
            if self.timer:
                self.timer.Stop()
        event.Skip()

    def RefreshNow(self):
        self.view.Refresh(True)
        self.view.Update()
        if wx.Platform == '__WXMAC__':
            self.noIdling = True
            wx.GetApp().Yield()
            self.noIdling = False

    def SetEditing(self, editing):
        self.isEditing = editing
        if not editing:
            self.SelectUiView(None)
            self.timer = wx.Timer(self.view)
            self.view.Bind(wx.EVT_TIMER, self.OnIdleTimer, self.timer)
            self.timer.Start(33)
        else:
            if self.timer:
                self.timer.Stop()

    def UpdateCursor(self):
        if self.tool:
            self.globalCursor = self.tool.GetCursor()
        else:
            self.globalCursor = None

        allUiViews = self.GetAllUiViews()
        if self.globalCursor:
            cur = wx.Cursor(self.globalCursor)
            self.view.SetCursor(cur)
            for uiView in allUiViews:
                if uiView.view:
                    uiView.view.SetCursor(cur)
        else:
            cursor = wx.CURSOR_ARROW
            self.view.SetCursor(wx.Cursor(cursor))
            for uiView in allUiViews:
                viewCursor = uiView.GetCursor()
                if uiView.view:
                    uiView.view.SetCursor(wx.Cursor(viewCursor if viewCursor else cursor))

    def OnIdleTimer(self, event):
        if not self.isEditing and not self.noIdling:
            self.uiCard.OnIdle(event)

    def SetTool(self, tool):
        if self.tool:
            self.tool.Deactivate()
        self.tool = tool
        if self.tool:
            self.tool.Activate()
        self.view.Refresh(True)
        self.UpdateCursor()

    def ClearAllViews(self):
        self.SelectUiView(None)
        for ui in self.uiViews.copy():
            if ui.model.type != "card":
                self.uiViews.remove(ui)
                ui.DestroyView()

    def CreateViews(self, cardModel):
        self.uiCard.SetModel(cardModel)
        self.uiViews = []
        self.AddUiViewsFromModels(cardModel.childModels, canUndo=False)  # Don't allow undoing card loads

    def GetAllUiViews(self):
        allUiViews = []
        for uiView in self.uiViews:
            allUiViews.append(uiView)
            if uiView.model.type == "group":
                allUiViews.extend(uiView.GetAllUiViews())
        return allUiViews

    def SetStackModel(self, model):
        self.ClearAllViews()
        model.SetStackView(self)
        self.stackModel = model
        self.cardIndex = None
        self.LoadCardAtIndex(0)
        self.view.SetSize(self.stackModel.GetProperty("size"))
        self.command_processor.ClearCommands()
        self.stackModel.SetDirty(False)
        self.UpdateCursor()

    def LoadCardAtIndex(self, index, reload=False):
        if index != self.cardIndex or reload == True:
            if not self.isEditing and self.cardIndex is not None and not reload:
                oldCardModel = self.stackModel.childModels[self.cardIndex]
                if self.runner:
                    self.runner.RunHandler(oldCardModel, "OnHideCard", None)
            self.cardIndex = index
            self.ClearAllViews()
            self.lastFocusedTextField = None
            if index is not None:
                cardModel = self.stackModel.GetCardModel(index)
                self.CreateViews(cardModel)
                self.SelectUiView(self.uiCard)
                self.view.Refresh(True)
                if self.designer:
                    self.designer.UpdateCardList()
                if not self.isEditing and self.runner:
                    self.runner.SetupForCard(cardModel)
                    if not reload:
                        if self.uiCard.model.GetHandler("OnShowCard"):
                            self.runner.RunHandler(self.uiCard.model, "OnShowCard", None)
                    self.noIdling = True
                    wx.GetApp().Yield()
                    self.noIdling = False

    def SetDesigner(self, designer):
        self.designer = designer

    def CopyModels(self, models):
        clipData = wx.CustomDataObject("org.cardstock.models")
        list = [model.GetData() for model in models]
        data = bytes(json.dumps(list).encode('utf8'))
        clipData.SetData(data)
        wx.TheClipboard.Open()
        wx.TheClipboard.SetData(clipData)
        wx.TheClipboard.Close()

    def Copy(self):
        self.CopyModels([ui.model for ui in self.selectedViews])

    def SelectAll(self):
        self.SelectUiView(None)
        for ui in self.uiViews:
            self.SelectUiView(ui, True)

    def CutModels(self, models, canUndo=True):
        self.CopyModels(models)
        if len(models) == 1 and models[0].type == "card":
            self.RemoveCard()
        elif len(models) > 0:
            deleteModels = [m for m in models if m.parent.type != "group"]
            command = RemoveUiViewsCommand(True, "Cut", self, self.cardIndex, deleteModels)
            self.command_processor.Submit(command, storeIt=canUndo)

    def Cut(self, canUndo=True):
        self.CutModels([ui.model for ui in self.selectedViews], canUndo)

    def Paste(self, canUndo=True):
        models = []
        if not wx.TheClipboard.IsOpened():  # may crash, otherwise
            if wx.TheClipboard.Open():
                if wx.TheClipboard.IsSupported(wx.DataFormat("org.cardstock.models")):
                    clipData = wx.CustomDataObject("org.cardstock.models")
                    if wx.TheClipboard.GetData(clipData):
                        rawdata = clipData.GetData()
                        list = json.loads(rawdata.tobytes().decode('utf8'))
                        models = [generator.StackGenerator.ModelFromData(self, dict) for dict in list]
                        if len(models) == 1 and models[0].type == "card":
                            models[0].SetProperty("name", models[0].DeduplicateName(models[0].GetProperty("name"),
                                                                                    [m.GetProperty("name") for m in
                                                                                     self.stackModel.childModels]))
                            command = AddNewUiViewCommand(True, "Paste Card", self, self.cardIndex + 1, "card", models[0])
                            self.command_processor.Submit(command, storeIt=canUndo)
                        else:
                            names = []
                            for model in models:
                                model.SetProperty("name",
                                                  self.uiCard.model.DeduplicateNameInCard(model.GetProperty("name"), None, names))
                                names.append(model.GetProperty("name"))
                            command = AddUiViewsCommand(True, 'Add Views', self, self.cardIndex, models)
                            self.command_processor.Submit(command, storeIt=canUndo)
                wx.TheClipboard.Close()
        return models

    def GroupSelectedViews(self):
        models = []
        for ui in self.uiViews:
            if ui.isSelected:
                models.append(ui.model)
        if len(models) >= 2:
            command = GroupUiViewsCommand(True, 'Group Views', self, self.cardIndex, models)
            self.command_processor.Submit(command)

    def UngroupSelectedViews(self):
        models = []
        for ui in self.uiViews:
            if ui.isSelected and ui.model.type == "group":
                models.append(ui.model)
        if len(models) >= 1:
            command = UngroupUiViewsCommand(True, 'Ungroup Views', self, self.cardIndex, models)
            self.command_processor.Submit(command)

    def GroupModelsInternal(self, models, group=None):
        if len(models) > 1:
            if not group:
                group = GroupModel(self)
                group.SetProperty("name", self.uiCard.model.GetNextAvailableNameInCard("group_"), False)
            for m in models:
                self.RemoveUiViewByModel(m)
            group.AddChildModels(models)
            self.AddUiViewsFromModels([group], False)
        return group

    def UngroupModelsInternal(self, groups):
        modelSets = []
        if len(groups) > 0:
            self.SelectUiView(None)
            for group in groups:
                childModels = []
                modelSets.append(childModels)
                for child in group.childModels.copy():
                    ui = self.GetUiViewByModel(child)
                    group.RemoveChild(child)
                    childModels.append(child)
                self.RemoveUiViewByModel(group)
                self.AddUiViewsFromModels(childModels, False)
        return modelSets

    def AddUiViewInternal(self, type, model=None):
        uiView = None

        if type == "button":
            uiView = UiButton(self.uiCard, self, model)
        elif type == "textfield" or type == "field":
            uiView = UiTextField(self.uiCard, self, model)
        elif type == "textlabel" or type == "label":
            uiView = UiTextLabel(self.uiCard, self, model)
        elif type == "image":
            uiView = UiImage(self.uiCard, self, model)
        elif type == "group":
            uiView = UiGroup(self.uiCard, self, model)
        elif type in ["pen", "line", "oval", "rect", "roundrect"]:
            uiView = UiShape(self.uiCard, self, type, model)

        if uiView:
            if uiView.view and not model:
                uiView.view.Center()
                uiView.model.SetProperty("position", uiView.view.GetPosition())
                uiView.model.SetProperty("size", uiView.view.GetSize())
            self.uiViews.append(uiView)
            uiView.model.parent = self.uiCard.model

            if uiView.model not in self.uiCard.model.childModels:
                self.uiCard.model.AddChild(uiView.model)

            if self.globalCursor:
                if uiView.view:
                    uiView.view.SetCursor(wx.Cursor(self.globalCursor))
        return uiView

    def AddUiViewsFromModels(self, models, canUndo=True):
        for model in models:
            if not model in self.uiCard.model.childModels:
                model.SetProperty("name", self.uiCard.model.DeduplicateNameInCard(model.GetProperty("name")))

        command = AddUiViewsCommand(True, 'Add Views', self, self.cardIndex, models)

        if canUndo:
            self.command_processor.Submit(command)
        else:
            # Don't mess with the Undo queue when we're just building a pgae
            command.Do()

        uiViews = self.uiViews[-len(models):]

        if self.globalCursor:
            for uiView in uiViews:
                if uiView.view:
                    uiView.view.SetCursor(wx.Cursor(self.globalCursor))

        return uiViews

    def GetSelectedUiViews(self):
        return self.selectedViews.copy()

    def SelectUiView(self, uiView, extend=False):
        if self.isEditing:
            if extend and uiView and uiView.parent and uiView.parent.model.type == "group":
                extend = False
            if extend and len(self.selectedViews) and self.selectedViews[0].parent and self.selectedViews[0].parent.model.type == "group":
                extend = False
            if extend and uiView and ((uiView.model.type == "card") != (len(self.selectedViews) and self.selectedViews[0].model.type == "card")):
                extend = False
            if len(self.selectedViews) and not extend:
                for ui in self.selectedViews:
                    ui.SetSelected(False)
                self.selectedViews = []
            if uiView:
                if extend and uiView in self.selectedViews:
                    uiView.SetSelected(False)
                    self.selectedViews.remove(uiView)
                else:
                    uiView.SetSelected(True)
                    self.selectedViews.append(uiView)
            if self.designer:
                self.designer.SetSelectedUiViews(self.selectedViews)

    def OnPropertyChanged(self, model, key):
        uiView = self.GetUiViewByModel(model)
        if model == self.stackModel:
            uiView = self.uiCard
            if key == "size":
                self.view.SetSize(model.GetProperty(key))
        if uiView:
            uiView.OnPropertyChanged(model, key)
        if uiView and self.designer:
            self.designer.cPanel.UpdatedProperty(uiView, key)

    def GetUiViewByModel(self, model):
        if model == self.uiCard.model:
            return self.uiCard
        for ui in self.GetAllUiViews():
            if ui.model == model:
                return ui
        return None

    def GetUiViewByName(self, name):
        if self.uiCard.model.properties["name"] == name:
            return self.uiCard
        for ui in self.GetAllUiViews():
            if ui.model.properties["name"] == name:
                return ui
        return None

    def RemoveUiViewByModel(self, viewModel):
        for ui in self.uiViews.copy():
            if ui.model == viewModel:
                if ui in self.selectedViews:
                    self.SelectUiView(ui, True)
                ui.model.parent = None
                if ui.model.type == "group":
                    ui.RemoveChildViews()
                self.uiViews.remove(ui)
                self.view.Refresh(True, rect=ui.model.GetRefreshFrame())
                self.uiCard.model.RemoveChild(ui.model)
                ui.DestroyView()
                return

    def ReorderSelectedViews(self, direction):
        oldIndexes = []
        for ui in self.selectedViews:
            if ui == self.uiCard or ui.model.parent.type == "group":
                return
            oldIndexes.append(self.uiCard.model.childModels.index(ui.model))
        oldIndexes.sort()

        if len(oldIndexes):
            firstIndex = oldIndexes[0]
            newIndexes = []
            for i in range(0, len(oldIndexes)):
                newIndex = 0
                if direction == "end":
                    newIndex = 0 + i
                elif direction == "fwd":
                    newIndex = firstIndex + 1 + i
                elif direction == "back":
                    newIndex = firstIndex - 1 + i
                elif direction == "front":
                    newIndex = len(self.uiCard.model.childModels) - len(oldIndexes) + i
                if newIndex < 0 or newIndex >= len(self.uiCard.model.childModels):
                    return
                newIndexes.append(newIndex)

            command = ReorderUiViewsCommand(True, "Reorder Views", self, self.cardIndex, oldIndexes, newIndexes)
            self.command_processor.Submit(command)

    def ReorderCurrentCard(self, direction):
        currentIndex = self.cardIndex
        newIndex = None
        if direction == "fwd": newIndex = currentIndex + 1
        elif direction == "back": newIndex = currentIndex - 1

        if newIndex < 0: newIndex = 0
        if newIndex >= len(self.stackModel.childModels): newIndex = len(self.stackModel.childModels) - 1

        if newIndex != currentIndex:
            command = ReorderCardCommand(True, "Reorder Card", self, self.cardIndex, newIndex)
            self.command_processor.Submit(command)

    def AddCard(self):
        newCard = CardModel(self)
        newCard.SetProperty("name", newCard.DeduplicateName("card_1",
                                                            [m.GetProperty("name") for m in self.stackModel.childModels]))
        command = AddNewUiViewCommand(True, "Add Card", self, self.cardIndex+1, "card", newCard)
        self.command_processor.Submit(command)

    def DuplicateCard(self):
        newCard = CardModel(self)
        newCard.SetData(self.stackModel.childModels[self.cardIndex].GetData())
        newCard.SetProperty("name", newCard.DeduplicateName(newCard.GetProperty("name"),
                                                            [m.GetProperty("name") for m in self.stackModel.childModels]))
        command = AddNewUiViewCommand(True, "Duplicate Card", self, self.cardIndex+1, "card", newCard)
        self.command_processor.Submit(command)

    def RemoveCard(self):
        index = self.cardIndex
        if len(self.stackModel.childModels) > 1:
            command = RemoveUiViewsCommand(True, "Remove Card", self, index, [self.stackModel.childModels[index]])
            self.command_processor.Submit(command)

    def OnMouseDown(self, uiView, event):
        if self.view.HasCapture() and event.LeftDClick():
            # Make sure we don't double-capture the mouse on GTK/Linux
            event.Skip()
            if uiView and uiView.model.type.startswith("text") and event.LeftDClick():
                # Flag this is a double-click  On mouseUp, we'll start the inline editor.
                self.isDoubleClick = True
            return

        pos = self.view.ScreenToClient(event.GetEventObject().ClientToScreen(event.GetPosition()))
        uiView = self.HitTest(pos, not event.ShiftDown())

        if self.inlineEditingView:
            if uiView == self.inlineEditingView:
                # Let the inline editor handle clicks while it's enabled
                event.Skip()
                return
            else:
                self.inlineEditingView.StopInlineEditing()

        if self.tool and self.isEditing:
            if uiView and uiView.model.type.startswith("text") and event.LeftDClick():
                # Flag this is a double-click  On mouseUp, we'll start the inline editor.
                self.isDoubleClick = True
            else:
                self.tool.OnMouseDown(uiView, event)
        else:
            uiView.OnMouseDown(event)
            event.Skip()

    def OnMouseMove(self, uiView, event):
        pos = self.view.ScreenToClient(event.GetEventObject().ClientToScreen(event.GetPosition()))
        if pos == self.lastMousePos:
            event.Skip()
            return

        uiView = self.HitTest(pos, not event.ShiftDown())

        if uiView != self.lastMouseMovedUiView:
            if not self.globalCursor:
                if uiView and uiView.GetCursor():
                    self.view.SetCursor(wx.Cursor(uiView.GetCursor()))
                else:
                    self.view.SetCursor(wx.Cursor(wx.CURSOR_ARROW))

        if self.inlineEditingView:
            # Let the inline editor handle clicks while it's enabled
            event.Skip()
            return

        if self.isEditing:
            if self.tool:
                self.tool.OnMouseMove(uiView, event)
        else:
            if uiView != self.lastMouseMovedUiView:
                if self.lastMouseMovedUiView:
                    self.lastMouseMovedUiView.OnMouseExit(event)
                if uiView:
                    uiView.OnMouseEnter(event)
            uiView.OnMouseMove(event)
            event.Skip()
            parent = uiView.parent
            while parent:
                parent.OnMouseMove(event)
                parent = parent.parent
        self.lastMouseMovedUiView = uiView
        self.lastMousePos = pos

    def OnMouseUp(self, uiView, event):
        pos = self.view.ScreenToClient(event.GetEventObject().ClientToScreen(event.GetPosition()))
        uiView = self.HitTest(pos, not event.ShiftDown())

        if self.inlineEditingView:
            # Let the inline editor handle clicks while it's enabled
            event.Skip()
            return

        if self.tool and self.isEditing:
            self.tool.OnMouseUp(uiView, event)
            if uiView and uiView.model.type.startswith("text") and self.isDoubleClick:
                # Fire it up!
                uiView.StartInlineEditing()
                event.Skip()
        else:
            uiView.OnMouseUp(event)
            event.Skip()
        self.isDoubleClick = False

    def OnMouseExit(self, event):
        if self.lastMouseMovedUiView:
            self.lastMouseMovedUiView.OnMouseExit(event)
        self.lastMouseMovedUiView = None

    def OnResize(self, event):
        self.UpdateBuffer()
        event.Skip()

    def UpdateBuffer(self):
        self.buffer = wx.Bitmap.FromRGBA(self.view.GetSize().Width, self.view.GetSize().Height)

    def OnPaint(self, event):
        if wx.Platform == '__WXMAC__':
            # Skip double-buffering on Mac, as it's much faster without it, and looks great
            dc = wx.PaintDC(self.view)
        else:
            if not self.buffer:
                self.UpdateBuffer()
            dc = wx.MemoryDC(self.buffer)

        gc = wx.GCDC(dc)
        bg = wx.Colour(self.uiCard.model.GetProperty("bgColor"))
        if not bg:
            bg = wx.Colour('white')
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(bg, wx.BRUSHSTYLE_SOLID))

        uiViews = self.GetAllUiViews()
        upd = wx.RegionIterator(self.view.GetUpdateRegion())
        paintUiViews = []
        while upd.HaveRects():
            updRect = upd.GetRect()
            if wx.Platform != '__WXMAC__':
                gc.DrawRectangle(updRect)
            for ui in uiViews:
                if ui not in paintUiViews and not ui.model.GetProperty("hidden"):
                    updRegion = wx.Region(wx.Rect(updRect.TopLeft - wx.Point(ui.model.GetAbsolutePosition()),
                                                  updRect.Size))

                    uiRegion = ui.GetHitRegion()
                    updRegion.Intersect(uiRegion)
                    if not uiRegion.IsEmpty():
                        paintUiViews.append(ui)
            upd.Next()

        if len(paintUiViews):
            for uiView in paintUiViews:
                uiView.Paint(gc)
            if self.isEditing:
                for uiView in paintUiViews:
                    uiView.PaintSelectionBox(gc)
        self.uiCard.PaintSelectionBox(gc)
        if self.tool:
            self.tool.Paint(gc)

        if wx.Platform != '__WXMAC__':
            wx.BufferedPaintDC(self.view, self.buffer)

    def HitTest(self, pt, selectedFirst=True):
        if selectedFirst:
            for uiView in self.selectedViews:
                if uiView.model.type != "card":
                    hit = uiView.HitTest(pt - wx.Point(uiView.model.GetAbsolutePosition()))
                    if hit == uiView:
                        return hit
        # Native views first
        for uiView in reversed(self.uiViews):
            if not uiView.model.GetProperty("hidden") and uiView.view:
                hit = uiView.HitTest(pt - wx.Point(uiView.model.GetAbsolutePosition()))
                if hit:
                    return hit
        # Then virtual views
        for uiView in reversed(self.uiViews):
            if not uiView.model.GetProperty("hidden") and not uiView.view:
                hit = uiView.HitTest(pt - wx.Point(uiView.model.GetAbsolutePosition()))
                if hit:
                    return hit
        return self.uiCard

    def OnKeyDown(self, uiView, event):
        if self.tool and self.isEditing:
            ms = wx.GetMouseState()
            if event.GetKeyCode() == wx.WXK_ESCAPE and not ms.LeftIsDown():
                self.designer.cPanel.SetToolByName("hand")
            self.tool.OnKeyDown(uiView, event)
        else:
            self.runner.OnKeyDown(event)
            self.uiCard.OnKeyDown(event)
            if uiView.model.type in ["textfield", "button"]:
                event.Skip()

    def OnKeyUp(self, uiView, event):
        if self.tool and self.isEditing:
            self.tool.OnKeyUp(uiView, event)
        else:
            self.runner.OnKeyUp(event)
            self.uiCard.OnKeyUp(event)
            if uiView.model.type == "textfield":
                event.Skip()

    def Undo(self):
        self.command_processor.Undo()
        if not self.command_processor.CanUndo():
            self.stackModel.SetDirty(False)
        self.view.Refresh(True)

    def Redo(self):
        self.command_processor.Redo()
        self.view.Refresh(True)

    def GetDesignerFindPath(self):
        cPanel = self.designer.cPanel
        cardModel = self.uiCard.model
        cardIndex = self.stackModel.childModels.index(cardModel)
        uiView = cPanel.lastSelectedUiView
        model = uiView.model if uiView else None

        start, end, text = self.designer.cPanel.GetInspectorSelection()
        if text:
            propName = cPanel.lastSelectedUiView.model.PropertyKeys()[cPanel.inspector.GetGridCursorRow()]
            return (str(cardIndex) + "." + model.GetProperty("name") + ".property." + propName, (start, end, text))

        start, end, text = self.designer.cPanel.GetCodeEditorSelection()
        handlerName = cPanel.currentHandler
        if model and handlerName:
            return (str(cardIndex) + "." + model.GetProperty("name") + ".handler." + handlerName, (start, end, text))

        if not model:
            model = self.uiCard.model
        return (str(cardIndex) + "." + model.GetProperty("name") + ".property." + model.PropertyKeys()[0], (0, 0, ""))

    def ShowDesignerFindPath(self, findPath, selectStart, selectEnd):
        if findPath:
            parts = findPath.split(".")
            # cardIndex, objectName, property|handler, key
            self.designer.cPanel.inspector.EnableCellEditControl(False)
            self.LoadCardAtIndex(int(parts[0]))
            self.SelectUiView(self.GetUiViewByName(parts[1]))
            if parts[2] == "property":
                wx.CallAfter(self.designer.cPanel.SelectInInspectorForPropertyName, parts[3], selectStart, selectEnd)
            elif parts[2] == "handler":
                wx.CallAfter(self.designer.cPanel.SelectInCodeForHandlerName, parts[3], selectStart, selectEnd)

    def GetViewerFindPath(self):
        cardModel = self.uiCard.model
        cardIndex = self.stackModel.childModels.index(cardModel)
        uiViews = self.GetAllUiViews()
        uiView = None
        if self.lastFocusedTextField in uiViews:
            uiView = self.lastFocusedTextField
        if not uiView:
            for ui in uiViews:
                if ui.model.type == "textfield" and ui.view.HasFocus():
                    uiView = ui
                    break
        if not uiView:
            for ui in uiView:
                if ui.model.type == "textfield":
                    uiView = ui
                    break

        if uiView:
            start, end = uiView.view.GetSelection()
            text = uiView.view.GetStringSelection()
            return (str(cardIndex) + "." + uiView.model.GetProperty("name") + ".property.text", (start, end, text))
        return None

    def ShowViewerFindPath(self, findPath, selectStart, selectEnd):
        if findPath:
            cardIndex, objectName, pathType, key = findPath.split(".")
            self.LoadCardAtIndex(int(cardIndex))
            uiView = self.GetUiViewByName(objectName)
            if uiView and uiView.view:
                uiView.view.SetFocus()
                uiView.view.SetSelection(selectStart, selectEnd)
