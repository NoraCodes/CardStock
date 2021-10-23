#!/usr/bin/python3

# viewer.py
"""
This is the root frame of the CardStock stack viewer application.  It also is used to run stacks from within
the designer, and is used to run the stack from a standalone, exported app as well.
It allows running and using a stack, and even saving its updated state, if the stack has its canSave flag set to True.

Another thing to note is that this class manages the nesting of stacks when calling RunStack() and ReturnFromStack().
The list stackStack is a stack of cardstock stacks, and keeps the runner, stackModel, filename, and current cardIndex
of each stack(file) in the stack(list).
"""

import os
import sys
import json
import wx
import wx.html
from stackManager import StackManager
from stackModel import StackModel
from uiCard import CardModel
from runner import Runner
import helpDialogs
from findEngineViewer import FindEngine
from wx.lib.mixins.inspection import InspectionMixin
from consoleWindow import ConsoleWindow
from codeRunnerThread import RunOnMainSync, RunOnMainAsync

HERE = os.path.dirname(os.path.abspath(__file__))

ID_MENU_FIND = wx.NewIdRef()
ID_MENU_FIND_SEL = wx.NewIdRef()
ID_MENU_FIND_NEXT = wx.NewIdRef()
ID_MENU_FIND_PREV = wx.NewIdRef()
ID_MENU_REPLACE = wx.NewIdRef()
ID_SHOW_CONSOLE = wx.NewIdRef()
ID_CLEAR_CONSOLE = wx.NewIdRef()

# ----------------------------------------------------------------------


class ViewerFrame(wx.Frame):
    """
    A ViewerFrame contains a stackManger's view, handles menu commands, manages the stack's runner, and the stack of stacks.
    """

    title = "CardStock"

    def __init__(self, parent, isStandalone, resMap=None):
        if isStandalone:
            self.title = os.path.basename(sys.executable)

        super().__init__(parent, -1, self.title, size=(500,500), style=wx.DEFAULT_FRAME_STYLE)

        self.stackManager = StackManager(self, False)
        self.stackManager.view.UseDeferredRefresh(True)
        if isStandalone and resMap:
            self.stackManager.resPathMan.SetPathMap(resMap)

        self.designer = None  # The designer sets this, if being run from the designer app
        self.isStandalone = isStandalone  # Are we running as a standalone app?
        self.Bind(wx.EVT_SIZE, self.OnResize)
        self.Bind(wx.EVT_CLOSE, self.OnClose)

        self.stackStack = []

        # The original runner for the stack that the user runs.  (As opposed to ones reached by RunStack().)
        self.rootRunner = None

        self.findDlg = None
        self.findEngine = FindEngine(self.stackManager)

        self.consoleWindow = ConsoleWindow(self)

    def Destroy(self):
        if self.consoleWindow:
            self.consoleWindow.Destroy()
            self.consoleWindow = None
        self.findEngine.stackManager = None
        self.findEngine = None
        self.designer = None
        self.stackManager = None
        return super().Destroy()

    def OnResize(self, event):
        if self.stackManager:
            if self.stackManager.stackModel.GetProperty("canResize"):
                self.stackManager.view.SetSize(self.GetClientSize())
        event.Skip()

    def SaveFile(self):
        if self.designer:
            self.designer.OnViewerSave(self.stackManager.stackModel)

        if self.stackManager.filename:
            data = self.stackManager.stackModel.GetData()
            try:
                jsonData = json.dumps(data, indent=2)
                with open(self.stackManager.filename, 'w') as f:
                    f.write(jsonData)
                self.stackManager.stackModel.SetDirty(False)
            except TypeError:
                # e = sys.exc_info()
                # print(e)
                wx.MessageDialog(None, str("Couldn't save file"), "", wx.OK).ShowModal()

    def MakeMenuBar(self):
        # create the file menu
        fileMenu = wx.Menu()
        if not self.isStandalone and not self.designer:
            fileMenu.Append(wx.ID_OPEN, "&Open\tCtrl-O", "Open Stack")
        if self.stackManager.filename and self.stackManager.stackModel.GetProperty("canSave"):
            fileMenu.Append(wx.ID_SAVE, "&Save\tCtrl-S", "Save Stack")
        if self.designer:
            fileMenu.Append(wx.ID_CLOSE, "&Close\tCtrl-W", "Close Stack")
        else:
            fileMenu.Append(wx.ID_EXIT, "&Quit\tCtrl-Q", "Quit Stack")

        editMenu = wx.Menu()
        editMenu.Append(wx.ID_UNDO, "&Undo\tCtrl-Z", "Undo Action")
        editMenu.Append(wx.ID_REDO, "&Redo\tCtrl-Shift-Z", "Redo Action")
        editMenu.AppendSeparator()
        editMenu.Append(wx.ID_CUT,  "C&ut\tCtrl-X", "Cut Selection")
        editMenu.Append(wx.ID_COPY, "&Copy\tCtrl-C", "Copy Selection")
        editMenu.Append(wx.ID_PASTE,"&Paste\tCtrl-V", "Paste Selection")
        editMenu.AppendSeparator()
        editMenu.Append(ID_MENU_FIND, "&Find...\tCtrl-F", "Find... in stack")
        editMenu.Append(ID_MENU_FIND_SEL, "&Find Selection\tCtrl-E", "Find Selection")
        editMenu.Append(ID_MENU_FIND_NEXT, "&Find Next\tCtrl-G", "Find Next in stack")
        editMenu.Append(ID_MENU_FIND_PREV, "&Find Previous\tCtrl-Shift-G", "Find Previous in stack")
        editMenu.Append(ID_MENU_REPLACE, "&Replace...\tCtrl-Shift-R", "Replace in stack")

        # and the help menu
        helpMenu = wx.Menu()
        helpMenu.Append(wx.ID_ABOUT, "&About\tCtrl-H", "About CardStock")
        helpMenu.Append(ID_SHOW_CONSOLE, "&Show/Hide Output Window\tCtrl-Alt-O", "Toggle Output Window")
        helpMenu.Append(ID_CLEAR_CONSOLE, "&Clear Output Window\tCtrl-Alt-C", "Clear Output Window")

        # and add them to a menubar
        menuBar = wx.MenuBar()
        if self.designer or fileMenu.GetMenuItemCount() > 1:
            menuBar.Append(fileMenu, "&File")
        menuBar.Append(editMenu, "&Edit")
        menuBar.Append(helpMenu, "&Help")
        self.SetMenuBar(menuBar)

        self.Bind(wx.EVT_MENU,   self.OnMenuOpen, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU,   self.OnMenuSave, id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU,   self.OnMenuClose, id=wx.ID_CLOSE)
        self.Bind(wx.EVT_MENU,   self.OnMenuClose, id=wx.ID_EXIT)

        self.Bind(wx.EVT_MENU,  self.OnMenuAbout, id=wx.ID_ABOUT)

        self.Bind(wx.EVT_MENU,  self.OnUndo, id=wx.ID_UNDO)
        self.Bind(wx.EVT_MENU,  self.OnRedo, id=wx.ID_REDO)
        self.Bind(wx.EVT_MENU,  self.OnCut, id=wx.ID_CUT)
        self.Bind(wx.EVT_MENU,  self.OnCopy, id=wx.ID_COPY)
        self.Bind(wx.EVT_MENU,  self.OnPaste, id=wx.ID_PASTE)

        self.Bind(wx.EVT_MENU, self.OnMenuFind, id=ID_MENU_FIND)
        self.Bind(wx.EVT_MENU, self.OnMenuFindSel, id=ID_MENU_FIND_SEL)
        self.Bind(wx.EVT_MENU, self.OnMenuFindNext, id=ID_MENU_FIND_NEXT)
        self.Bind(wx.EVT_MENU, self.OnMenuFindPrevious, id=ID_MENU_FIND_PREV)
        self.Bind(wx.EVT_MENU, self.OnMenuReplace, id=ID_MENU_REPLACE)

        self.Bind(wx.EVT_MENU, self.OnMenuShowConsoleWindow, id=ID_SHOW_CONSOLE)
        self.Bind(wx.EVT_MENU, self.OnMenuClearConsoleWindow, id=ID_CLEAR_CONSOLE)

    wildcard = "CardStock files (*.cds)|*.cds|All files (*.*)|*.*"

    def OpenFile(self, filename):
        if self.stackManager.filename and self.stackManager.stackModel.GetProperty("canSave") and self.stackManager.stackModel.GetDirty():
            r = wx.MessageDialog(None, "There are unsaved changes. Do you want to Save first?",
                                 "Save before Closing?", wx.YES_NO | wx.CANCEL).ShowModal()
            if r == wx.ID_CANCEL:
                return
            if r == wx.ID_YES:
                self.SaveFile()
        wx.GetApp().OpenFile(filename)

    def OnMenuOpen(self, event):
        if self.stackManager.filename and self.stackManager.stackModel.GetProperty("canSave") and self.stackManager.stackModel.GetDirty():
            r = wx.MessageDialog(None, "There are unsaved changes. Do you want to Save first?",
                                 "Save before Closing?", wx.YES_NO | wx.CANCEL).ShowModal()
            if r == wx.ID_CANCEL:
                return
            if r == wx.ID_YES:
                self.SaveFile()

        initialDir = os.getcwd()
        if self.stackManager.filename:
            initialDir = os.path.dirname(self.stackManager.filename)
        dlg = wx.FileDialog(self, "Open CardStock file...", initialDir,
                           style=wx.FD_OPEN, wildcard = self.wildcard)
        self.stackManager.view.Enable(False)
        if dlg.ShowModal() == wx.ID_OK:
            filename = dlg.GetPath()
            dlg.Destroy()
            wx.GetApp().OpenFile(filename)
        else:
            dlg.Destroy()
            wx.CallLater(50, self.stackManager.view.Enable, True) # Needed to avoid a MSWindows FileDlg bug

    def OnMenuSave(self, event):
        self.SaveFile()

    def OnMenuClose(self, event):
        self.Close()
        self.Refresh()

    def OnClose(self, event):
        if self.stackManager.filename and self.stackManager.stackModel.GetProperty("canSave") and self.stackManager.stackModel.GetDirty():
            r = wx.MessageDialog(None, "There are unsaved changes. Do you want to Save first?",
                                 "Save before Quitting?", wx.YES_NO | wx.CANCEL).ShowModal()
            if r == wx.ID_CANCEL:
                event.Veto()
                return
            if r == wx.ID_YES:
                self.SaveFile()

        if not self.stackManager.runner.stopRunnerThread:
            for l in range(len(self.stackStack)-1):
                self.PopStack(None, True)

            self.stackManager.SetDown()
            if self.consoleWindow:
                self.consoleWindow.Destroy()
                self.consoleWindow = None
            event.Skip()

    def OnCut(self, event):
        f = self.FindFocus()
        if f and hasattr(f, "Cut"):
            f.Cut()

    def OnCopy(self, event):
        f = self.FindFocus()
        if f and hasattr(f, "Copy"):
            f.Copy()

    def OnPaste(self, event):
        f = self.FindFocus()
        if f and hasattr(f, "Paste"):
            f.Paste()

    def OnUndo(self, event):
        f = self.FindFocus()
        if f and hasattr(f, "Undo"):
            if not hasattr(f, "CanUndo") or f.CanUndo():
                f.Undo()
                return
        event.Skip()

    def OnRedo(self, event):
        f = self.FindFocus()
        if f and hasattr(f, "Redo"):
            if not hasattr(f, "CanRedo") or f.CanRedo():
                f.Redo()
                return
        event.Skip()

    def ShowFindDialog(self, isReplace):
        if self.findDlg:
            self.findDlg.Close(True)
        self.findDlg = wx.FindReplaceDialog(self, self.findEngine.findData,
                                            'Replace' if isReplace else 'Find', style=int(isReplace))
        self.findDlg.Bind(wx.EVT_FIND_CLOSE, self.OnFindClose)
        self.findDlg.Bind(wx.EVT_FIND, self.OnFindEvent)
        self.findDlg.Bind(wx.EVT_FIND_NEXT, self.OnFindEvent)
        self.findDlg.Bind(wx.EVT_FIND_REPLACE, self.OnReplaceEvent)
        self.findDlg.Bind(wx.EVT_FIND_REPLACE_ALL, self.OnReplaceAllEvent)
        self.findDlg.Bind(wx.EVT_CLOSE, self.OnFindClose)
        self.findDlg.Show()

    def OnMenuFind(self, event):
        self.ShowFindDialog(False)

    def OnMenuReplace(self, event):
        self.ShowFindDialog(True)

    def OnFindClose(self, event):
        self.findDlg.Destroy()
        self.findDlg = None

    def OnMenuFindSel(self, event):
        self.findEngine.UpdateFindTextFromSelection()

    def OnMenuFindNext(self, event):
        flags = self.findEngine.findData.GetFlags()
        self.findEngine.findData.SetFlags(flags | 1)
        self.findEngine.Find()
        self.findEngine.findData.SetFlags(flags)

    def OnMenuFindPrevious(self, event):
        flags = self.findEngine.findData.GetFlags()
        self.findEngine.findData.SetFlags(flags & ~1)
        self.findEngine.Find()
        self.findEngine.findData.SetFlags(flags)

    def OnFindEvent(self, event):
        self.findEngine.Find()

    def OnReplaceEvent(self, event):
        self.findEngine.Replace()

    def OnReplaceAllEvent(self, event):
        self.findEngine.ReplaceAll()

    def OnMenuAbout(self, event):
        dlg = helpDialogs.CardStockAbout(self)
        dlg.ShowModal()
        dlg.Destroy()

    def OnMenuShowConsoleWindow(self, event):
        if self.consoleWindow.IsShown():
            self.consoleWindow.Hide()
        else:
            self.consoleWindow.Show()

    def OnMenuClearConsoleWindow(self, event):
        self.consoleWindow.Clear()

    def GosubStack(self, filename, cardNumber, ioValue):
        # Enter here on a Runner thread
        # Go into, or back out of, another stack
        # Push a stack if a filename is given, else pop
        # ioValue is the setupValue or the returnValue
        # return True iff successful
        if filename:
            # push
            try:
                if not os.path.isabs(filename):
                    filename = os.path.join(os.path.dirname(self.stackManager.filename), filename)
                with open(filename, 'r') as f:
                    data = json.load(f)
                if data:
                    @RunOnMainAsync
                    def func():
                        # switch over to the main thread
                        stackModel = StackModel(None)
                        stackModel.SetData(data)
                        self.PushStack(stackModel, filename, cardNumber, ioValue)
                    func()
                    return True
            except (TypeError, FileNotFoundError):
                return False
        else:
            # pop
            if len(self.stackStack) > 1:
                @RunOnMainAsync
                def func():
                    # switch over to the main thread
                    self.PopStack(ioValue)
                func()
                return True
            else:
                return False

    def PushStack(self, stackModel, filename, cardIndex, setupValue=None):
        if len(self.stackStack) > 0:
            self.stackStack[-1][3] = self.stackManager.cardIndex
            self.stackManager.runner.StopTimers()

        runner = Runner(self.stackManager, self)
        if len(self.stackStack) == 0:
            self.rootRunner = runner

        self.stackStack.append([runner, stackModel, filename, cardIndex])
        self.RunViewer(runner, stackModel, filename, cardIndex, setupValue, False)

    def PopStack(self, returnValue, isShuttingDown=False):
        if len(self.stackStack) > 1:
            sModel = self.stackManager.stackModel
            def onFinished(runner):
                runner.errors = None  # Not the root stack, so we're not reporting any errors here upon return to the designer
                sModel.SetDown()
                sModel.DismantleChildTree()

            self.stackManager.runner.onRunFinished = onFinished
            self.stackManager.runner.CleanupFromRun()

            self.stackStack.pop()
            parts = self.stackStack[-1]

            if not isShuttingDown:
                parts[1].SetBackUp(self.stackManager)
                self.RunViewer(*parts, returnValue, True)
            else:
                self.stackManager.runner = parts[0]
                self.stackManager.SetStackModel(parts[1], True)

    def SetupViewerSize(self):
        # Size the stack viewer window for the new stack, and allow resizing only if canResize==True

        if wx.Platform != "__WXGTK__":
            self.SetMaxClientSize(wx.DefaultSize)
            self.SetMinClientSize(wx.DefaultSize)

        cs = self.stackManager.stackModel.GetProperty("size")

        self.stackManager.view.SetSize(cs)
        self.stackManager.UpdateBuffer()
        self.SetClientSize(cs)

        if wx.Platform != "__WXGTK__":
            # TODO: Allow disabling resizing on Linux / GTK
            # It's disabled currently due to bugs in converting Frame to Client sizing on that platform
            if self.stackManager.stackModel.GetProperty("canResize"):
                self.SetMinClientSize(wx.Size(200,200))
            else:
                self.SetMaxClientSize(cs)
                self.SetMinClientSize(cs)

    def RunViewer(self, runner, stackModel, filename, cardIndex, ioValue, isGoingBack):
        # Load the model, start the runner, and handle ioValues(setup and return values) for pushed/popped stacks
        self.stackManager.SetStackModel(stackModel, True)
        self.stackManager.filename = filename

        if self.designer:
            runner.onRunFinished = self.designer.OnRunnerFinished
        if not isGoingBack:
            runner.stackSetupValue = ioValue
        self.stackManager.runner = runner
        self.MakeMenuBar()
        self.SetupViewerSize()

        if self.designer:
            runner.AddSyntaxErrors(self.designer.cPanel.codeEditor.analyzer.syntaxErrors)
        if not isGoingBack:
            self.stackManager.stackModel.RunSetup(runner)
        self.stackManager.LoadCardAtIndex(None)
        if not (0 <= cardIndex < len(self.stackManager.stackModel.childModels)):
            cardIndex = 0
        self.stackManager.LoadCardAtIndex(cardIndex)
        if isGoingBack:
            runner.DoReturnFromStack(ioValue)


# ----------------------------------------------------------------------

class ViewerApp(wx.App, InspectionMixin):
    def OnInit(self):
        self.argFilename = None
        self.doneStarting = False
        self.Init(self)  # for InspectionMixin
        self.locale = wx.Locale(wx.LANGUAGE_ENGLISH)
        self.SetAppDisplayName('CardStock')
        self.frame = None

        return True

    def NewFile(self):
        if self.frame:
            self.frame.Hide()
            self.frame.Destroy()

        self.frame = ViewerFrame(None, False)
        self.frame.PushStack(self.frame.stackManager.stackModel, None, 0)
        self.SetTopWindow(self.frame)
        self.frame.Show(True)

    def OpenFile(self, filename):
        if filename:
            try:
                with open(filename, 'r') as f:
                    data = json.load(f)
                if data:
                    if self.frame:
                        self.frame.Hide()
                        self.frame.stackManager.SetDown()
                        self.frame.Destroy()

                    stackModel = StackModel(None)
                    stackModel.SetData(data)
                    self.frame = ViewerFrame(None, False)
                    self.frame.PushStack(stackModel, filename, 0)
                    self.SetTopWindow(self.frame)
                    self.frame.Show(True)
            except TypeError:
                # e = sys.exc_info()
                # print(e)
                wx.MessageDialog(None, str("Couldn't read file"), "", wx.OK).ShowModal()

    def MacReopenApp(self):
        """
        Restore the main frame (if it's minimized) when the Dock icon is
        clicked on OSX.
        """
        top = self.GetTopWindow()
        if top and top.IsIconized():
            top.Iconize(False)
        if top:
            top.Raise()

    def MacOpenFile(self, filename):
        self.argFilename = filename
        if self.doneStarting:
            self.frame.OpenFile(self.argFilename)

# ----------------------------------------------------------------------


def RunViewer():
    app = ViewerApp(redirect=False)

    if len(sys.argv) > 1 and not app.argFilename:
        app.argFilename = sys.argv[1]

    if app.argFilename:
        app.OpenFile(app.argFilename)
    else:
        app.NewFile()

    app.doneStarting = True
    app.argFilename = None

    app.MainLoop()


if __name__ == '__main__':
    RunViewer()