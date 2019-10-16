# -*- coding: utf-8 -*-

# This code is part of Qiskit.
#
# (C) Copyright IBM 2019.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""
Main GUI frontend interface for Metal.
@author: Zlatko
"""

import sys
import logging
import traceback
import importlib

from pathlib import Path

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt, QDir
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMainWindow, QDockWidget
from PyQt5.QtWidgets import QTextEdit, QLineEdit, QMessageBox
from PyQt5.QtWidgets import QAction, QInputDialog, QFileDialog
from PyQt5.QtWidgets import QLabel

from .. import logger, save_metal, load_metal
from ..draw_utility import plot_simple_gui_spawn, plot_simple_gui_style
from ..draw_utility import draw_all_objects

from . import widgets
from .widgets.toolbar_icons import add_toolbar_icon
from .widgets.dialog_create_metal import Dialog_create_metal
from .widgets.trees.metal_objects import Tree_Metal_Objects
from .widgets.trees.default_options import Tree_Default_Options
from .widgets.log_window import Logging_Window_Widget, Logging_Hander_for_Log_Widget
from ._handle_qt_messages import catch_exception_slot_pyqt

class Metal_gui(QMainWindow):
    myappid = u'qiskit.metal.main_gui'
    _window_title = "Qiskit Metal - Quantum VLSI and Sims"

    def __init__(self, circ, OBJECTS=None, DEFAULT_OPTIONS=None):
        '''
        When running in IPython and Jupyter, make sure you have the QT loop launched.

        .. code-block python
            %matplotlib qt
            %gui qt
            from qiskit_metal import Metal_gui, PlanarCircuit

            layout = PlanarCircuit()
            gui = Qiskit_Metal_GUI(layout)
        '''

        self._setup_qApp()

        super().__init__()

        # params
        self.circ = circ
        self._OBJECTS = None
        self._DEFAULT_OPTIONS = None

        # set params
        self.set_OBJECTS(OBJECTS)
        self.set_DEFAULT_OPTIONS(DEFAULT_OPTIONS)

        # create workspace
        self._setup_main_window()
        self._setup_menu_bar()
        self._setup_plot()
        self._setup_tree_view()
        self._setup_tree_circ_options()
        self._setup_tree_default_options()
        self._setup_menu_bar_final()
        self._setup_window_style()
        self._setup_main_toolbar()
        self._setup_logging()

        # refresh
        self.show()
        self.refresh_all()
        self.raise_()

    def _setup_qApp(self):
        self.logger = logger

        self.qApp = QApplication.instance()
        if self.qApp is None:
            self.logger.error(r"""ERROR: QApplication.instance is None.
            Did you run a cell with the magic in IPython?
            ```python
                %gui qt
            ```
            This command allows IPython to integrate itself with the Qt event loop,
            so you can use both a GUI and an interactive prompt together.
            Reference: https://ipython.readthedocs.io/en/stable/config/eventloops.html
            """)

        if sys.platform.startswith('win'):
            # For window only
            # Arbitrary string, needed for icon in taskbar to be custom set proper
            # https://stackoverflow.com/questions/1551605/how-to-set-applications-taskbar-icon-in-windows-7
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(self.myappid)

    def _setup_main_window(self):
        self.setWindowTitle(self._window_title)

        self.imgs_path = Path(widgets.__file__).parent.parent / '_imgs'
        if not self.imgs_path.is_dir():
            print(f'Metal Main Window: Bad file path for loading images! {self.imgs_path}')
        else:
            icon = QIcon(str(self.imgs_path/'qiskit_logo1.png'))
            self.setWindowIcon(icon)
            # try not sur eif works:
            self.icon_tray = QtWidgets.QSystemTrayIcon(icon, self)
            self.icon_tray.show()
            self.qApp.setWindowIcon(icon)

        self.setDockOptions(QMainWindow.AllowTabbedDocks |
                            QMainWindow.AllowNestedDocks)
        self.setAnimated(True)

        # Dummy
        self.setCentralWidget(QTextEdit())
        self.centralWidget().hide()

        self.resize(1200, 850)
        # Resize events are handled by self.resizeEvent()

    def _setup_logging(self, catch_exceptions=True):
        '''
        Make logging window and handle traceback exceptions
        based on: https://stackoverflow.com/questions/28655198/best-way-to-display-logs-in-pyqt
        '''
        # Log window widget
        self.logger_window = Logging_Window_Widget(self.imgs_path)

        # Handlers
        self.logger_window.add_logger('Metal')
        self._log_handler = Logging_Hander_for_Log_Widget('Metal', self)
        logger.addHandler(self._log_handler)  # logger is the metal logger Metal

        # TODO: Make modular and add pyEPR
        # if 0:
        #     self.logger_window.add_logger('pyEPR')
        #     self._log_handler_pyEPR = logging.getLogger('pyEPR')
        #     self._log_handler_pyEPR.addHandler(self._log_handler_pyEPR)

        # Handle exceptions with tracebakck
        def excepthook(type, value, tb):
            """
            This function prints out a given traceback and exception to sys.stderr.
            When an exception is raised and uncaught, the interpreter calls sys.excepthook
            h three arguments, the exception class, exception instance, and a traceback object.
            In an interactive session this happens just before control is returned to the
            prompt; in a Python program this happens just before the program exits.
            The handling of such top-level exceptions can be customized by assigning another
            three-argument function to sys.excepthook.
            """
            traceback_string = '\n'.join(traceback.format_exception(type, value, tb))
            self.logger_window.log_message_to('Errors', traceback_string)
            traceback.print_exception(type, value, tb)

        self._logger_excepthook = excepthook
        if catch_exceptions:
            sys.excepthook = excepthook

        # Add dock, position and style
        self.logView_dock = self._add_dock('Logs', self.logger_window, 'Right')
        self.tabifyDockWidget(self.tree_def_ops.dock, self.logView_dock)

    def _setup_menu_bar(self):
        self.menu = self.menuBar()
        self.menu_file = self.menu.addMenu("File")
        self.menu_view = self.menu.addMenu("View")
        self.menu_act = self.menu.addMenu("Actions")

        self.menu_file.addAction("Save")
        self.menu_file.addSeparator()
        self.menu_file.addAction("Quit")

    def _setup_menu_bar_final(self):
        '''
        Finish off a few things after all core items have been created,
        Especially the tree views. Link them in the toolbar.
        '''
        # Menus
        self.menu_view.tight_action = action = QAction('Tight layout')
        action.triggered.connect(self.fig_tight_layout)
        self.menu_view.tight = self.menu_view.addAction(action)
        self.fig_tight_layout()

    def _setup_plot(self):
        fig_draw, ax_draw = plot_simple_gui_spawn(dict(num=None))
        self.fig_draw = fig_draw
        self.fig_window = self.fig_draw.canvas.window()
        self.ax_draw = ax_draw

        self.draw_dock = self._add_dock(
            'Drawing window', self.fig_window, 'Left', 400)

        # Custom toolbars
        toolbar = self.fig_draw.canvas.manager.toolbar
        menu = self.menu_act

        add_toolbar_icon(toolbar, 'action_refresh_plot',
                         self.imgs_path/'refresh-button.png',
                         self.re_draw,
                         'Refresh plot only',
                         'R', menu)

        toolbar.addSeparator()

        add_toolbar_icon(toolbar, 'action_draw_connectors',
                         self.imgs_path/'connectors_draw.png',
                         self.draw_connectors,
                         'Draw all connectors of circ object',
                         'Shift+C', menu)

        toolbar.addSeparator()

        self.fig_draw.show()

    def _setup_main_toolbar(self):
        self.toolbar_main_func = self.addToolBar(
            'Main functions')  # tood have htis add a menu show hide
        toolbar = self.toolbar_main_func
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        menu = self.menu_act

        add_toolbar_icon(toolbar, 'action_refresh_all',
                         self.imgs_path/'refresh-all.png',
                         self.refresh_all,
                         'Refresh all trees and plots in the gui.',
                         'Ctrl+R', menu,
                         label="Refresh\nall")

        add_toolbar_icon(toolbar, 'action_remake_all_objs',
                         self.imgs_path/'gears.png',
                         self.remake_all,
                         'Remake all objects with their current parameters',
                         'M', menu,
                         label="Remake\nall")

        add_toolbar_icon(toolbar, 'action_clear_all_objects',
                         self.imgs_path/'clear-button.png',
                         self.clear_all_objects,
                         'Clear\nall',
                         None, menu,
                         label='Clear\nall')

        toolbar.addSeparator()

        add_toolbar_icon(toolbar, 'action_gds_export',
                         self.imgs_path/'GDS.png',
                         self.action_gds_export,
                         'Export\nto gds',
                         None, menu,
                         label='Export\nto gds')

        add_toolbar_icon(toolbar, 'action_save_metal',
                         self.imgs_path/'save.png',
                         self.action_save_metal,
                         'Save metal circ object',
                         None, menu,
                         label='Save\ncircuit')

        add_toolbar_icon(toolbar, 'action_open_metal',
                         self.imgs_path/'open.png',
                         self.action_open_metal,
                         'Open metal saved file',
                         None, menu,
                         label='Load\ncircuit')

        self._setup_create_objects()

    def _setup_create_objects(self):

        # Decide if tree library might betbter probably . for now just quick here
        self.toolbar_create_metal = self.addToolBar('Create Metal')
        toolbar = self.toolbar_create_metal
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        # toolbar.setIconSize(QSize(50,50))
        # toolbar.setStyleSheet("""
        #    QAction {
        #        font-size: 2pt;
        #        font: 6px;
        #    }""")

        #####
        # Labels
        toolbar.title_Label = QLabel("Create\nmetal")
        toolbar.title_Label.setAlignment(QtCore.Qt.AlignCenter)
        toolbar.title_Label.setStyleSheet("""
            QLabel {
                background-color : #A7ADBA;
                color: #101112;
                padding: 4px;
                border: none;
                font-size: 4pt;
                border-style: outset;
                border-width: 0px;
                border-radius: 5px;
                font: bold 12px;
                padding: 5px;
            }""")  # Move to stylesheet        border-color: #6c94c0;       color: #38413B; background-color : #DAE4EF;             min-width: 7em;
        toolbar.addWidget(toolbar.title_Label)

        ####
        # Create buttons
        from ..config import CREATE_METAL_CLASSES
        for metal_class in CREATE_METAL_CLASSES:
            self.add_metal_object(toolbar, metal_class)

    def add_metal_object(self, toolbar,
                         metal_class_name,
                         tool_name=None):
        '''
        Creates wrapper function
        '''

        assert isinstance(metal_class_name, str)

        class_name = metal_class_name.split('.')[-1]
        try:
            module = importlib.import_module(metal_class_name)
        except ImportError as error:
            self.logger.error(
                f'add_metal_object: Could not load object module for the toolbar.\n Failed to load {metal_class_name}\n Please check the name path and that the file does not have errors. \nError ({error}): \n{sys.exc_info()}')
            return False
        try:
            metal_class = getattr(module, class_name)
        except Exception as error:
            self.logger.error(
                f'add_metal_object: Loaded module {class_name} but could not find/load class {class_name}\nError ({error}): \n{sys.exc_info()}')
            return False

        if not tool_name:
            tool_name = class_name

        def create_metal_obj(*args):
            # Load module  on the fly
            # Assumed that the module file name is the same as the class name

            nonlocal class_name
            nonlocal metal_class
            #class_name = metal_class_name.split('.')[-1]
            #metal_class = getattr(module, class_name)

            form = Dialog_create_metal(self, metal_class)
            result, my_args = form.get_params()
            if result:
                if my_args['name']:
                    metal_class(self.circ, my_args['name'], options=my_args['options'])
                    self.refresh_all()

        # Label
        label = tool_name.replace('_', ' ')
        if label.startswith('Metal '):
            label = label[6:]
        if len(label) > 14:
            label = label[:int(len(label)/2)] + '-\n' + \
                label[int(len(label)/2):]  # split to new line

        # Image path
        img = (self.imgs_path/getattr(metal_class, '_img')) \
            if hasattr(metal_class, '_img') else None
        if not Path(img).is_file():
            img2 = self.imgs_path/'Metal_Object.png'
            logger.warning(f'Could not locate  image path {img}')
            if Path(img2).is_file():
                img = img2
                logger.warning(f'Replacing with  image path {img}')
            else:
                logger.warning(f'Could not even find base image path {img2}')

        # Add tool
        add_toolbar_icon(toolbar, tool_name, img, create_metal_obj, label=label)

        setattr(self, 'create_'+tool_name, create_metal_obj)

        return True

    def _setup_tree_view(self):

        tree = self.tree = Tree_Metal_Objects(self, OBJECTS=self.OBJECTS, gui=self)
        tree.main_window = QMainWindow(self)
        tree.dock = self._add_dock('Object Explorer', tree.main_window, 'Right', 400)
        tree.dock.setToolTip('Press ENTER after done editing a value to remake the objects.')

        tree.dock.setToolTipDuration(2000)
        # Specifies how long time the tooltip will be displayed, in milliseconds. If the value
        # is -1 (default) the duration is calculated depending on the length of the tooltip.

        # Main window for tree
        tree.main_window.setCentralWidget(tree)
        #main_window.layout_ = QVBoxLayout(self.tree_window)
        # dock.setMinimumWidth(250) # now set the real min width, the first one set the width

        # Toolbar
        # toolbar = main_window.toolbar = main_window.addToolBar(
        #    'Objects Properties Toolbar')
        #tree.add_toolbar_refresh(toolbar, main_window, self.imgs_path)
        #tree.add_toolbar_slider(toolbar, main_window, self.imgs_path)

    def _setup_tree_default_options(self):

        tree = self.tree_def_ops = Tree_Default_Options(
            self, content_dict=self.DEFAULT_OPTIONS, gui=self)
        tree.main_window = QMainWindow(self)
        tree.dock = self._add_dock('Default Properties', tree.main_window, 'Right', 400)
        tree.dock.setToolTip('Press ENTER after done editing a value to remake the objects.')
        tree.dock.setToolTipDuration(2000)

        # Main window for tree
        tree.main_window.setCentralWidget(tree)
        tree.resizeColumnToContents(0)

    def _setup_tree_circ_options(self):
        tree = self.tree_circ_ops = Tree_Default_Options(
            self, content_dict=self.circ.params, gui=self)
        tree.main_window = QMainWindow(self)
        tree.dock = self._add_dock('Circuit Properties', tree.main_window, 'Right', 400)

        # Main window for tree
        tree.main_window.setCentralWidget(tree)
        self.tabifyDockWidget(self.tree_circ_ops.dock, self.tree.dock)
        tree.resizeColumnToContents(0)

    def load_stylesheet(self, path=None):
        """Load and set stylesheet for the main gui

        Keyword Arguments:
            path {[str]} -- [Path tos tylesheet. Can also de default] (default: {None})
        """

        if path == 'default':
            self.setStyleSheet(path)
            return True

        if path is None:
            path = self.imgs_path.parent/'style_sheets'/'metal_default.qss'
        path = Path(path)

        if path.is_file():
            stylesheet = path.read_text()
            # TODO: replace all :/ with the corrent path or handle correctly

            self.setStyleSheet(stylesheet)
        else:
            self.logger.error('Could not find the stylesheet file where expected %s', path)
            return False

        return True

    def _setup_window_style(self):

        # TODO: Not sure this works correctly, probably needs to be fixed
        QDir.setCurrent(str(self.imgs_path.parent))  # should not do this here, change parth
        QtCore.QDir.addSearchPath(':', str(self.imgs_path))

        self.load_stylesheet()

        # fusion macintosh # windows
        self.setStyle(QtWidgets.QStyleFactory.create("fusion"))
        #self.fig_window.statusBar().setStyleSheet(f'''QLabel{{ {base} }}''')

    def _add_dock(self, name, widget, location, minimum_width=None):
        '''
        location: Left, Right, ...
        '''

        dock = QDockWidget(name)

        # Sets the widget for the dock widget to widget.
        # If the dock widget is visible when widget is added, you must show() it explicitly.
        # Note that you must add the layout of the widget before you call this function; if not, the widget will not be visible.
        dock.setWidget(widget)

        # A floating dock widget is presented to the user as an independent window "on top" of its parent QMainWindow,
        # instead of being docked in the QMainWindow.
        dock.setFloating(False)

        # Add Menu button show/hide to main window
        self.menu_view.addAction(dock.toggleViewAction())

        # Add to main window
        self.addDockWidget(getattr(Qt, location+'DockWidgetArea'), dock)

        if minimum_width:
            dock.setMinimumWidth(minimum_width)

        return dock

    def _logging_remove_handler(self, handler, logger_):
        """Remove logging handler when closing window

        Arguments:
            logger_ {[type]} -- [description]
            handler {[type]} -- [description]
        """
        for i, handler in enumerate(logger_.handlers):
            if handler is handler:
                logger_.handlers.pop(i)
                break

    def closeEvent(self, event):
        """[This event handler is called with the given event when Qt receives a window close request for a top-level widget from the window system.

            By default, the event is accepted and the widget is closed. ]

        Arguments:
            event {[type]} -- [description]
        """
        try:
            self._logging_remove_handler(self._log_handler, logger)
            if 0:
                self._logging_remove_handler(self._log_handler_pyEPR, logging.getLogger('pyEPR'))
        except Exception as e:
            print(f'Error while closing main gui window: {e}')
        finally:
            super().closeEvent(event)

    ##########################################################################################

    def re_draw_func(self, x):
        """
        Function used when processing the drawing
        Can overwrite to scale. THis is somewhat legacy code,but can be useful
        still

        Example redefinition:
            lambda x: scale_objs(x, 1E3, 1E3, 1E3,(0,0))

        Arguments:
            x {[Dict]} -- [Dict of obecjts ]

        Returns:
            [Dict] -- [Affine transofrmed objects]
        """
        return x

    @catch_exception_slot_pyqt()
    def re_draw(self, *args):  # pylint: disable=unused-argument
        '''
        Calls draw_all_objects. Does correct handling of gui figure.
        The *args is to handle pyQtSlots
        '''
        logger.debug('Redrawing')
        self.fig_window.setStatusTip('Redrawing')
        self.fig_draw.canvas.hide()
        self.ax_draw.clear_me()

        try:
            draw_all_objects(self.OBJECTS, ax=self.ax_draw,
                             func=self.re_draw_func)
        except Exception:
            self.logger.error('\n\n'+traceback.format_exc())
            # Alternative:     exc_info = sys.exc_info()  traceback.print_exception(*exc_info)

        plot_simple_gui_style(self.ax_draw)

        self.fig_draw.canvas.show()
        self.fig_draw.canvas.draw()
        self.fig_window.setStatusTip('Redrawing:DONE')

    @catch_exception_slot_pyqt()
    def refresh_tree(self, *args):  # pylint: disable=unused-argument
        """
        Refresh the OBJECTS tree
        Calls repopulate on the Tree
        """
        self.tree.rebuild()  # change name to refresh?
        # self.tree_def_ops.refresh()

    @catch_exception_slot_pyqt()
    def refresh_tree_default_options(self, *args):  # pylint: disable=unused-argument
        """
        Refresh the tree with default options.
        Calls repopulate on the Tree
        """
        self.tree_def_ops.rebuild()

    @catch_exception_slot_pyqt()
    def refresh_all(self, *args):  # pylint: disable=unused-argument
        """
        Refresh all trees and plots and entire gui
        """
        self.re_draw()
        self.refresh_tree()
        self.refresh_tree_default_options()
        # print('self.tree_circ_ops.rebuild()')
        self.tree_circ_ops.rebuild()

    @catch_exception_slot_pyqt()
    def remake_all(self, *args):  # pylint: disable=unused-argument
        """
        Remake all objects and refresh plots
        """
        logger.info('Remaking all Metal objects from options')
        self.circ.make_all_objects()
        self.re_draw()

    @catch_exception_slot_pyqt()
    def draw_connectors(self, *args):  # pylint: disable=unused-argument
        """
        Draw all connetors
        args used for pyqt socket
        """
        self.circ.plot_connectors(ax=self.ax_draw)
        self.fig_draw.canvas.draw()

    @property
    def OBJECTS(self):
        """
        Returns:
            [Dict] -- [Handle to Circuit's OBJECTS]
        """
        return self._OBJECTS

    def set_OBJECTS(self, OBJECTS):
        '''
        Should ideally only ever have 1 instance object of OBJECTS
        '''
        if OBJECTS is None:
            OBJECTS = self.circ.OBJECTS
        self._OBJECTS = OBJECTS
        if hasattr(self, 'tree'):
            self.tree.change_content_dict(OBJECTS)

    @property
    def DEFAULT_OPTIONS(self):
        """ Gets the DEFAULT_OPTIONS

        Returns:
            [Dict] -- [DEFAULT_OPTIONS]
        """
        return self._DEFAULT_OPTIONS

    def set_DEFAULT_OPTIONS(self, DEFAULT_OPTIONS):
        '''
        Should ideally only ever have 1 instance object of OBJECTS
        '''
        if DEFAULT_OPTIONS is None:
            from ..draw_functions import DEFAULT_OPTIONS
        self._DEFAULT_OPTIONS = DEFAULT_OPTIONS
        if hasattr(self, 'tree_def_ops'):
            self.tree_def_ops.change_content_dict(self._DEFAULT_OPTIONS)

    def resizeEvent(self, event):
        """
        Handles the resize event of the main window.
        Overwrittes parent class.
        Does not require a connect this way.

        QT:
        ----------------
        This event handler can be reimplemented in a subclass to receive widget
        resize events which are passed in the event parameter. When resizeEvent()
        is called, the widget already has its new geometry. The old size is
        accessible through QResizeEvent::oldSize().

        The widget will be erased and receive a paint event immediately after
        processing the resize event. No drawing need be (or should be) done inside
        this handler.

        Arguments:
            event {[(QResizeEvent]} -- [https://doc.qt.io/qt-5/qresizeevent.html]
        """
        ans = super().resizeEvent(event)
        self.fig_draw.tight_layout()
        # QApplication.instance().processEvents() # not needed
        return ans

    def fig_tight_layout(self):
        """Utility function, Does tight layout and redraw
        """
        self.fig_draw.tight_layout()
        self.fig_draw.canvas.draw()

    def getText(self, description="Select name", name='Name of new object:'):
        """Opens a QT dialog to get text, Utility function

        Keyword Arguments:
            description {str} -- [Dialog description displayed in gui when it pops us] (default: {"Select name"})
            name {str} -- [Dialog name] (default: {'Name of new object:'})

        Returns:
            [str or None] -- text from dialog or none is the test is '' or user cancels
        """
        text, ok_pressed = QInputDialog.getText(self, description, name, QLineEdit.Normal, "")
        if ok_pressed and text != '':
            return text
        return None

    @catch_exception_slot_pyqt()
    def clear_all_objects(self, *args):  # pylint: disable=unused-argument
        """
        Called by gui to clear all objects. Checks first with use dialog
        *args is required for the PyQt5 Socket
        """
        ret = QMessageBox.question(self, '', "Are you sure you want to clear all Metal objects?",
                                   QMessageBox.Yes | QMessageBox.No)
        if ret == QMessageBox.Yes:
            self.circ.clear_all_objects()
            self.refresh_all()

    @catch_exception_slot_pyqt()
    def action_gds_export(self, *args):  # pylint: disable=unused-argument
        """
        Handles click on export to gds
        """
        filename = QFileDialog.getSaveFileName(None,
                                               'Select locaiton to export GDS file to')[0]
        if filename:
            self.circ.gds_draw_all(filename)

    @catch_exception_slot_pyqt()
    def action_save_metal(self, *args):  # pylint: disable=unused-argument
        """
        Handles click on save circ
        """
        filename = QFileDialog.getSaveFileName(None,
                                               'Select locaiton to save Metal objects and circ to')[0]
        if filename:
            save_metal(filename, self.circ)
            logger.info(f'Successfully save metal to {filename}')

    @catch_exception_slot_pyqt()
    def action_open_metal(self, *args):  # pylint: disable=unused-argument
        """
        Handles click on loading metal circuit
        """
        filename = QFileDialog.getOpenFileName(None,
                                               'Select locaiton to save Metal objects and circ to')[0]
        if filename:
            circ = load_metal(filename)  # do_update=True
            self.change_circ(circ)
            logger.info(f'Successfully loaded file\n file={filename}')

    def change_circ(self, circ):
        """Used in loading

        Arguments:
            circ {[Metal_Circ_Base instance]} -- [new circuit]
        """
        self.circ = circ
        self.set_OBJECTS(self.circ.OBJECTS)
        self.tree_circ_ops.change_content_dict(self.circ.params)
        self.logger.info('Changed circuit, updated default dictionaries, etc.')
        self.refresh_all()