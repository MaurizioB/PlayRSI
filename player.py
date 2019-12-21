#!/usr/bin/env python3

import os
import re
from math import sqrt
import pyaudio
import numpy as np
import pydub
from PyQt5 import QtCore, QtGui, QtWidgets, QtNetwork, uic

if os.environ.get('XDG_CURRENT_DESKTOP'):
    if os.environ['XDG_CURRENT_DESKTOP'].strip().lower() == 'kde':
        if not os.environ['KDE_FULL_SESSION'].strip().lower() == 'true':
            os.environ.update({'KDE_FULL_SESSION': ''})
    else:
        os.environ.update({'KDE_FULL_SESSION': ''})
else:
    os.environ.update({'KDE_FULL_SESSION': ''})

VolumeStep = 10

findIndex = re.compile('\d+')
baseUrl = 'https://lsaplus.swisstxt.ch/audio/{}_96.stream/'
playlistFile = 'chunklist_DVR.m3u8'

shortNames = 'uno', 'due', 'tre'
radioNames = tuple('rete{}'.format(n) for n in shortNames)
radioTitles = tuple('Rete{}'.format(n.title()) for n in shortNames)

StartRole = QtCore.Qt.UserRole + 1000
EndRole = StartRole + 1


class Player(QtCore.QObject):
    ActiveState, SuspendedState, StoppedState, IdleState = range(4)
    request = QtCore.pyqtSignal(int)

    def __init__(self, parent):
        super().__init__(parent)
        self.pyaudio = pyaudio.PyAudio()
        self.stream = None
        self.nextData = None
        self.currentState = self.StoppedState
        self._volume = 1
#        self.curve = QtCore.QEasingCurve(QtCore.QEasingCurve.InCubic)

    def setVolume(self, volume):
        volume = volume * .01
#        self._volume = self.curve.valueForProgress(volume)
#        self._volume = sin(radians(90 * volume))
        self._volume = pow(2.0, (sqrt(sqrt(sqrt(volume))) * 192 - 192.)/6.0)
#        self._volume = 1 - sqrt(1 - volume ** 2)

    def setFileNameTemplate(self, pre, post):
        self.pre = pre
        self.post = post

    def setRadio(self, radio):
        self.path = self.parent().cacheDirs[radio]

    def getData(self, index, radio=None):
        if radio is not None:
            self.setRadio(radio)
        segment = pydub.AudioSegment.from_file('{}/{}{}{}'.format(
            self.path, self.pre, index, self.post))
        data = segment.get_array_of_samples()
        array = np.array(data).reshape(2, -1, order='F').swapaxes(1, 0)
        return array

    def start(self, index, radio=None):
        print('started?!')
        if not self.stream:
            self.stream = self.pyaudio.open(
                format=8, channels=2, rate=44100, 
                start=False, output=True, 
                stream_callback=self.readData)

        if self.currentState == self.SuspendedState:
            self.stream.start_stream()
            self.currentState = self.ActiveState
        else:
            self.currentIndex = index
            self.currentData = self.getData(index, radio)

            self.bytePos = 512
            self.stream.start_stream()
            self.currentState = self.ActiveState
            self.request.emit(index + 1)
            self.overlapping = False

    def pause(self):
        if self.stream:
            self.stream.stop_stream()
            self.currentState = self.SuspendedState

    def stop(self):
        if self.stream:
            self.stream.stop_stream()
            self.currentState = self.StoppedState
            self.currentData = self.nextData = None
            self.overlapping = False

    def getNextData(self):
#        overlap = 1024
#        overlap = 256
        overlap = 2048
        nextData = self.getData(self.currentIndex + 1)
#        half = overlap // 2
#        self.currentData[-overlap:] += nextData[half:half + overlap]
#        self.nextData = nextData[half + overlap:]
        self.currentData[-overlap:] += nextData[:overlap]
        self.nextData = nextData[overlap:]
        self.overlapping = False
        print('done', len(self.currentData))

    def readData(self, _, frameCount, timeInfo, status):
        data = self.currentData[self.bytePos:self.bytePos + frameCount]
#        if not len(data):
#            print('no data!')
#            self.currentState = self.StoppedState
#            return None, pyaudio.paComplete
        dataLen = len(data)
        if dataLen < frameCount:
            print('troppo corto, accodo prossimo chunk', self.bytePos)
            self.currentIndex += 1
            self.currentData = self.nextData
            self.nextData = None
            diff = frameCount - dataLen
            data = np.concatenate((data, self.currentData[:diff]))
            self.bytePos = diff
            print('diff', diff)
#            print(self.bytePos, len(self.currentData), self.currentIndex)
            if not len(data):
                print('no data!')
                self.currentState = self.StoppedState
                return None, pyaudio.paComplete
            self.request.emit(self.currentIndex + 1)
        else:
            self.bytePos += frameCount
            if self.bytePos + frameCount * 100 > len(self.currentData) and self.nextData is None and not self.overlapping:
                self.overlapping = True
                QtCore.QTimer.singleShot(0, self.getNextData)
                print('overlapping', len(self.currentData))
#                nextData = self.getData(self.currentIndex + 1)
#                self.currentData[-1024:] += nextData[:1024]
#                print('done', len(self.currentData))
#                self.nextData = nextData[1024:]
#            if self.bytePos + frameCount * 10 > len(self.currentData):
#                print('sto per cambiare')
#                newData = self.getData(self.currentIndex + 1)
#                print('ok!', len(self.currentData), len(newData), type(self.currentData), type(newData))
#                self.currentData = np.concatenate((self.currentData, newData))
        data *= self._volume
        return data.tostring(), pyaudio.paContinue
#            self.notify.emit((currentTime() - self.currentTime).total_seconds())
#        try:
#            self.waveIODevice.stop()
#        except:
#            pass
        

#    def readData(self, maxlen):
#        if self.bytePos >= self.waveLength:
#            self.finished.emit()
#            return None
#
#        nextPos = self.bytePos + maxlen / self.waveMultiplier
#        data = self.outputWaveData[self.bytePos:nextPos]
#
#        if self.infinite and nextPos >= self.waveLength:
#            nextPos = maxlen / self.waveMultiplier - len(data)
#            data = np.concatenate((data, self.outputWaveData[:nextPos]))
#
#        self.bytePos = nextPos
#        
#        return data.tostring()

class RadioButton(QtWidgets.QPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMinimumSize(96, 40)
        self.buttonPixmap = None

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.buttonPixmap:
            qp = QtGui.QPainter(self)
            qp.setRenderHints(qp.SmoothPixmapTransform)
            opt = QtWidgets.QStyleOptionButton()
            self.initStyleOption(opt)
            rect = self.style().subElementRect(QtWidgets.QStyle.SE_PushButtonContents, opt, self)
            margin = self.style().pixelMetric(QtWidgets.QStyle.PM_ButtonMargin, opt, self)
            rect.adjust(margin, margin, -margin, -margin)
            pm = self.buttonPixmap.scaled(rect.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            pmRect = pm.rect()
            pmRect.moveCenter(rect.center())
            qp.drawPixmap(pmRect, pm)


class VolumeSlider(QtWidgets.QWidget):
    volumeChanged = QtCore.pyqtSignal(int)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
#        self.muteIcon = QtGui.QIcon.fromTheme('audio-volume-muted')
#        self.lowIcon = QtGui.QIcon.fromTheme('audio-volume-low')
#        self.mediumIcon = QtGui.QIcon.fromTheme('audio-volume-medium')
#        self.currentIcon = self.highIcon = QtGui.QIcon.fromTheme('audio-volume-high')
        self.muteIcon = QtGui.QIcon('audio-volume-muted.svg')
        self.lowIcon = QtGui.QIcon('audio-volume-low.svg')
        self.mediumIcon = QtGui.QIcon('audio-volume-medium.svg')
        self.currentIcon = self.highIcon = QtGui.QIcon('audio-volume-high.svg')

        self.baseWidth = QtWidgets.QPushButton().sizeHint().height()
        self.iconSize = self.style().pixelMetric(QtWidgets.QStyle.PM_ButtonIconSize, None, self)
        self.setFixedWidth(self.baseWidth)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.slider.hide()
        self.slider.setFocusPolicy(QtCore.Qt.NoFocus)
        self.slider.setMaximum(100)
        self.slider.setValue(100)
        self.slider.setTickPosition(self.slider.TicksBothSides)
        self.slider.setTickInterval(25)
        self.slider.setFixedWidth(80)
        self.slider.valueChanged.connect(self.volumeChanged)
        self.slider.valueChanged.connect(self.updateVolume)
        self.volume = self.slider.value
        self.setVolume = self.slider.setValue
        self.slider.installEventFilter(self)
        self.isClicking = False

        absoluteClickButtons = self.style().styleHint(QtWidgets.QStyle.SH_Slider_AbsoluteSetButtons, 
            None, self.slider)
        for i, b in enumerate((QtCore.Qt.LeftButton, QtCore.Qt.MiddleButton, QtCore.Qt.RightButton)):
            if b & absoluteClickButtons:
                self.absoluteClickButton = b
                break
        else:
            self.absoluteClickButton = None

        self.expandAnimation = QtCore.QParallelAnimationGroup(self)
        self.expandAnimation.addAnimation(QtCore.QPropertyAnimation(self, b"minimumWidth"))
        self.expandAnimation.addAnimation(QtCore.QPropertyAnimation(self, b"maximumWidth"))
        for a in range(2):
            ani = self.expandAnimation.animationAt(a)
            ani.setDuration(100)
            ani.setStartValue(self.baseWidth)
            ani.setEndValue(self.baseWidth + 82)

        self.leaveTimer = QtCore.QTimer(singleShot=True, interval=500, timeout=self.collapse)

    def updateVolume(self, volume):
        self.oldVolume = volume
        if not volume:
            self.currentIcon = self.muteIcon
        elif volume < 33:
            self.currentIcon = self.lowIcon
        elif volume < 66:
            self.currentIcon = self.mediumIcon
        else:
            self.currentIcon = self.highIcon
        self.update()
        if volume:
            self.setToolTip('{}%'.format(volume))
        else:
            self.setToolTip('Mute')
        if self.isVisible():
            rect = self.rect().translated(self.mapToGlobal(QtCore.QPoint()))
            pos = QtGui.QCursor.pos()
            if not pos in rect:
                pos = QtCore.QPoint(pos.x(), self.mapToGlobal(self.rect().center()).y())
            QtWidgets.QToolTip.showText(pos, self.toolTip(), self)
#            print(QtGui.QCursor.pos() in rect)

    def eventFilter(self, source, event):
        # create a fake event to avoid custom style or proxystyle
        if event.type() == QtCore.QEvent.MouseButtonPress and self.absoluteClickButton and not self.isClicking:
            event = QtGui.QMouseEvent(event.type(), event.pos(), 
                self.absoluteClickButton, self.absoluteClickButton, 
                event.modifiers())
            self.isClicking = True
            QtWidgets.QApplication.sendEvent(source, event)
            self.isClicking = False
            return True
        elif event.type() == QtCore.QEvent.Wheel:
            self.wheelEvent(event)
            event.accept()
            return True
        return super().eventFilter(source, event)

    def collapse(self):
        self.expandAnimation.setDirection(self.expandAnimation.Backward)
        self.expandAnimation.start()

    def enterEvent(self, event):
        self.leaveTimer.stop()
        if (self.expandAnimation.state() != self.expandAnimation.Running and 
            self.maximumWidth() == self.expandAnimation.animationAt(0).startValue()):
                self.expandAnimation.setDirection(self.expandAnimation.Forward)
                self.expandAnimation.start()
                self.slider.show()
                r = self.slider.geometry()
                r.moveTo(self.baseWidth + 2, (self.height() - self.slider.height()) / 2)
                self.slider.setGeometry(r)

    def leaveEvent(self, event):
        self.leaveTimer.start()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            r = QtCore.QRect(0, 0, self.baseWidth, self.baseWidth)
            if event.pos() in r:
                if self.volume():
                    oldVolume = self.volume()
                    self.setVolume(0)
                    self.oldVolume = oldVolume
                else:
                    self.setVolume(self.oldVolume if self.oldVolume else 10)

    def mouseMoveEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton:
            self.setVolume(event.x())

    def wheelEvent(self, event):
        step = self.slider.pageStep()
        if event.angleDelta().y() < 0 or event.angleDelta().x() < 0:
            step *= -1
        self.setVolume(self.volume() + step)
        print('vln', self.volume())
        screenPos = self.mapToGlobal(QtCore.QPoint())
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), self.toolTip(), self, self.rect().translated(-screenPos))
        event.accept()

#    def resizeEvent(self, event):
#        self.mask = QtGui.QPainterPath()
#        rect = self.rect()
#        rect.setHeight(24)
#        rect.moveCenter(self.rect().center())
#        self.mask.moveTo(rect.bottomLeft())
#        self.mask.lineTo(rect.topRight())
#        self.mask.lineTo(rect.bottomRight())
#        self.mask.closeSubpath()

    def paintEvent(self, event):
        qp = QtGui.QPainter(self)
        qp.setRenderHints(qp.Antialiasing)
        qp.translate(.5, .5)

        baseSize = self.baseWidth - 4
        centerY = QtCore.QRectF(self.rect()).center().y()
        rect = QtCore.QRectF(0, 0, baseSize, baseSize)
        rect.moveCenter(QtCore.QPointF(self.baseWidth / 2, centerY - 1))
        qp.drawRoundedRect(rect.toRect(), 2, 2)

        iconSize = self.iconSize
        pos = (self.height() - iconSize) / 2 - 1
        qp.drawPixmap(pos - 1, pos, self.currentIcon.pixmap(iconSize))

#        if self.sliderShown:
#            qp.translate(self.baseWidth + 2, centerY)
#            qp.drawPath(self.sliderPath)


class LiveButton(QtWidgets.QToolButton):
    wasDown = False
    def mousePressEvent(self, event):
        self.wasDown = self.isDown()
        if not self.isDown():
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pass

    def mouseReleaseEvent(self, event):
        if self.isDown():
            if not self.wasDown:
                self.clicked.emit()
        else:
            print('wtf')
            super().mouseReleaseEvent(event)


class SeekSlider(QtWidgets.QWidget):
    valueChanged = QtCore.pyqtSignal(int)
    hourBackground = QtGui.QColor(255, 255, 255, 192)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
#        self.setMouseTracking(True)

        fm = self.fontMetrics()
        charWidths = max([fm.width(str(n)) for n in range(10)])
        self.hourWidth = charWidths * 2 + 2
        self.hourMinuteWidth = self.hourWidth * 2 + fm.width(':')

        self.topMargin = fm.height()

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.slider.setFocusPolicy(QtCore.Qt.NoFocus)
        self.slider.valueChanged.connect(self.update)
        self.slider.valueChanged.connect(self.valueChanged)
        self.slider.installEventFilter(self)
        self.maximum = self.slider.maximum
        self.value = self.slider.value
        self.setValue = self.slider.setValue
        self.slider.setMaximum(2160)
        self.oldValue = self.maximum()
        self.setValue(self.maximum())
        self.slider.setMouseTracking(True)

        self.sliderOption = QtWidgets.QStyleOptionSlider()

        self.setFixedHeight(self.topMargin + self.slider.minimumSizeHint().height())

        palette = self.palette()
        self.halfPen = palette.color(palette.Dark)
        self.quarterPen = palette.color(palette.Mid)

    def updateLabelPositions(self):
        timeReference = self.window().timeReference()
        self.timeLabels = []
        self.ticks = []

        opt = QtWidgets.QStyleOptionSlider()
        self.slider.initStyleOption(opt)
        style = self.slider.style()
        grooveRect = style.subControlRect(QtWidgets.QStyle.CC_Slider, 
            opt, QtWidgets.QStyle.SC_SliderGroove, self.slider)
        handleRect = style.subControlRect(QtWidgets.QStyle.CC_Slider, 
            opt, QtWidgets.QStyle.SC_SliderHandle, self.slider)
        sliderLength = handleRect.width()
        sliderMin = grooveRect.x()
        sliderMax = grooveRect.right() - sliderLength + 1
        self.minTick = style.sliderPositionFromValue(0, 2160, 
            0, sliderMax - sliderMin) + handleRect.width() / 2
        maxTick = style.sliderPositionFromValue(0, 2160, 
            2160, sliderMax - sliderMin) + handleRect.width()

        tickDiff = maxTick - self.minTick
        self.hourSize = (tickDiff) / 6
        self.quarterSize = (tickDiff) / 24
        minuteSize = tickDiff / 360

        self.hourTicks = []
        self.halfTicks = []
        self.quarterTicks = []

        self.leftHour = timeReference.hour() - 6
        if timeReference.minute():
            self.leftHour += 1
            self.leftHour %= 24
        m = 0
        x = self.minTick - (timeReference.minute()) * minuteSize
        while x <= maxTick:
            m %= 4
            if x >= self.minTick:
                if not m:
                    self.hourTicks.append(x)
                elif m == 2:
                    self.halfTicks.append(x)
                else:
                    self.quarterTicks.append(x)
            x += self.quarterSize
            if round(x, 2) == int(x):
                x = int(x)
            m += 1
        self.update()

    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.MouseMove:
            res = super().eventFilter(source, event)
            self.slider.initStyleOption(self.sliderOption)
            handleRect = self.slider.style().subControlRect(QtWidgets.QStyle.CC_Slider, 
                self.sliderOption, QtWidgets.QStyle.SC_SliderHandle, self.slider)
            if self.slider.isSliderDown():
                value = self.slider.value()
                pos = self.slider.mapToGlobal(handleRect.center())
            else:
                value = self.slider.style().sliderValueFromPosition(0, 2160, 
                    event.x(), self.sliderMax - self.sliderMin + handleRect.width())
                pos = event.globalPos()
                pos.setY(self.slider.mapToGlobal(handleRect.center()).y())
                if event.pos() in self.grooveRect:
                    if self.minTick > event.x():
                        value = 0
                    elif self.maxTick < event.x():
                        value = 2160
            secs = (2160 - value) * 10
            time = self.window().timeReference().addSecs(-secs)
            QtWidgets.QToolTip.showText(pos, time.toString('HH:mm:ss'), self)
            return res
        return super().eventFilter(source, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.slider.setGeometry(self.rect().adjusted(0, self.topMargin, 0, 0))
        self.updateLabelPositions()

        self.slider.initStyleOption(self.sliderOption)
        style = self.slider.style()
        self.grooveRect = style.subControlRect(QtWidgets.QStyle.CC_Slider, 
            self.sliderOption, QtWidgets.QStyle.SC_SliderGroove, self.slider)
        handleRect = style.subControlRect(QtWidgets.QStyle.CC_Slider, 
            self.sliderOption, QtWidgets.QStyle.SC_SliderHandle, self.slider)
        sliderLength = handleRect.width()
        self.sliderMin = self.grooveRect.x()
        self.sliderMax = self.grooveRect.right() - sliderLength + 1
        self.minTick = style.sliderPositionFromValue(0, 2160, 
            0, self.sliderMax - self.sliderMin) + handleRect.width() / 2
        self.maxTick = style.sliderPositionFromValue(0, 2160, 
            2160, self.sliderMax - self.sliderMin) + handleRect.width()

    def paintEvent(self, event):
        qp = QtGui.QPainter(self)

        if self.hourSize >= 48:
            qp.save()
            y = self.topMargin * .7
            qp.setPen(self.halfPen)
            for tick in self.halfTicks:
                qp.drawLine(tick, y, tick, self.topMargin)
            if self.quarterSize >= 16:
                qp.setPen(self.quarterPen)
                y = self.topMargin * .85
                for tick in self.quarterTicks:
                    qp.drawLine(tick, y, tick, self.topMargin)
            qp.restore()

        hourRect = QtCore.QRect(2, 0, self.hourSize - 2, self.topMargin)
        hour = self.leftHour
        fm = self.slider.fontMetrics()
        lastTextRect = None
        for tick in self.hourTicks:
            # first draw ticks, as labels have to paint over them
            qp.drawLine(tick, 0, tick, self.topMargin)
        for tick in self.hourTicks:
            timeStr = '{:02}:00'.format(hour)
            textRect = fm.boundingRect(hourRect.translated(tick, 0), 
                QtCore.Qt.AlignLeft|QtCore.Qt.AlignTop, timeStr).adjusted(0, 0, 2, 0)
            if lastTextRect and lastTextRect.intersects(textRect):
                lastTextRect = None
                continue
            lastTextRect = textRect
            qp.save()
            qp.setPen(QtCore.Qt.NoPen)
            qp.setBrush(self.hourBackground)
            qp.drawRoundedRect(textRect, 2, 2)
            qp.restore()
            qp.drawText(textRect, 
                QtCore.Qt.AlignLeft|QtCore.Qt.AlignTop,
                timeStr)
            hour += 1
            hour %= 24
        if self.hourTicks[0] > self.minTick + textRect.width() + 4:
#            qp.drawLine(self.minTick, y, self.minTick, self.topMargin)
            timeStr = self.window().timeReference().addSecs(-21600).toString('HH:mm')
            textRect = fm.boundingRect(hourRect.translated(self.minTick, 0), 
                QtCore.Qt.AlignLeft|QtCore.Qt.AlignTop, timeStr).adjusted(0, 0, 2, 0)
            qp.save()
            qp.setPen(QtCore.Qt.NoPen)
            qp.setBrush(self.hourBackground)
            qp.drawRoundedRect(textRect, 2, 2)
            qp.restore()
            qp.drawText(textRect, 
                QtCore.Qt.AlignLeft|QtCore.Qt.AlignTop,
                timeStr)


class RecordDock(QtWidgets.QDockWidget):
    closed = QtCore.pyqtSignal()
    unfloat = QtCore.pyqtSignal()
    def __init__(self, parent, show=False):
        super().__init__(parent)
        self.setWindowIcon(QtGui.QIcon('record.svg'))
        self.setFloating(True)
        if not show:
            self.hide()
        self.setAllowedAreas(QtCore.Qt.NoDockWidgetArea)
        self.floatButton = self.findChild(QtWidgets.QAbstractButton, 'qt_dockwidget_floatbutton')
        self.floatButton.clicked.connect(self.unfloat)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


class TrayIcon(QtWidgets.QSystemTrayIcon):
    pass


def getTime(t):
    return t.toString('d HH:mm:ss')


class DurationDelegate(QtWidgets.QStyledItemDelegate):
    def displayText(self, secs, locale):
        mins, secs = divmod(secs, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return '{}:{:02}:{:02}'.format(hours, mins, secs)
        return '{:02}:{:02}'.format(mins, secs)


class RecordModel(QtGui.QStandardItemModel):
    # will be SortFilterProxyModel from filesystem!
    def __init__(self, parent):
        super().__init__(parent)
        self.getRecordings()

    def getRecordings(self):
        # clearing will clear the currentIndex, selection and other things...
        # subclass from AbstractItemModel or existing subclasses instead!
        self.clear()
        self.setHorizontalHeaderLabels(['Network', 'Start', 'End', 'Duration'])

        from random import randrange
        self.recordings = [[], [], []]
        for radio, (radioName, radioTitle) in enumerate(zip(radioNames, radioTitles)):
            radioItem = QtGui.QStandardItem(radioTitle)
            radioItem.setIcon(QtGui.QIcon('{}.png'.format(radioName)))
            self.appendRow(radioItem)

            randomString = 'randomtext' * 100
            for r in range(randrange(1, 5)):
                recordItem = QtGui.QStandardItem('Recording {} {}'.format(r + 1, randomString[:randrange(128)]))
                now = QtCore.QDateTime.currentDateTime()
                start = now.addDays(-randrange(1)).addSecs(-randrange(86400))
                duration = min(randrange(0, 7200), start.secsTo(now.addSecs(-10)))
                end = start.addSecs(duration)
                startItem = QtGui.QStandardItem()
                startItem.setData(start, QtCore.Qt.DisplayRole)
                endItem = QtGui.QStandardItem()
                endItem.setData(end, QtCore.Qt.DisplayRole)
                # this will have a item delegate...
                durationItem = QtGui.QStandardItem()
                durationItem.setData(start.secsTo(end), QtCore.Qt.DisplayRole)
                durationItem.setTextAlignment(QtCore.Qt.AlignRight|QtCore.Qt.AlignVCenter)
#                print(getTime(start), getTime(end), end.secsTo(now), getTime(now), start < end, end < now)

                radioItem.appendRow([recordItem, startItem, endItem, durationItem])

#            radioItem.setText('bsbuba')
#            radioItem.appendRow([startItem])

#    def rowCount(self, parent):
#        if not parent.isValid():
#            return 3
        


class RsiPlayer(QtWidgets.QMainWindow):
    shown = False
    recordDockShown = False

    def __init__(self):
        super().__init__()
        uic.loadUi('player.ui', self)

        self.settings = QtCore.QSettings()
        defaultRadio = self.settings.value('defaultRadio', 0, type=int)
        cacheDirs = QtCore.QStandardPaths.standardLocations(
            QtCore.QStandardPaths.AppDataLocation)
        self.cacheDirs = []
        try:
            for cacheDir in cacheDirs:
                cd = QtCore.QFileInfo(cacheDir)
                if not cd.exists():
                    assert QtCore.QDir().mkpath(cd.absoluteFilePath())
                rootDir = QtCore.QDir(cd.absoluteFilePath())
                for radioDir in radioNames:
                    self.cacheDirs.append(rootDir.absoluteFilePath(radioDir))
                    if not rootDir.exists(radioDir):
                        rootDir.mkpath(radioDir)
                if cd.isWritable():
                    break
        except Exception as e:
            print('TODO create temp dir?', e)

        self.radioPixmaps = []
        self.radioIcons = []

        for radio, radioName in enumerate(radioNames, 1):
            btn = getattr(self, 'rete{}Btn'.format(radio))
            pixmap = QtGui.QPixmap('{}.png'.format(radioName))
            btn.buttonPixmap = pixmap
            self.radioPixmaps.append(pixmap)
            self.radioIcons.append(QtGui.QIcon(pixmap))

        self.trayIcon = TrayIcon(self.radioIcons[1])
        if self.useTrayIcon():
            self.trayIcon.show()
        self.trayIcon.activated.connect(self.trayClicked)

        self.playCache = {r:{} for r in range(3)}

        self.radioGroup.setId(self.rete1Btn, 0)
        self.radioGroup.setId(self.rete2Btn, 1)
        self.radioGroup.setId(self.rete3Btn, 2)
        self.radioGroup.buttonToggled[QtWidgets.QAbstractButton, bool].connect(self.setRadio)

        self.playToggleBtn.setIcon(QtGui.QIcon('play.png'))
        self.playToggleBtn.toggled.connect(self.togglePlay)
#        self.playToggleBtn.setFixedHeight(self.seekSlider.minimumHeight())

        self.seekSlider.valueChanged.connect(self.seek)

        self.liveBtn.clicked.connect(self.goLive)

        self.queue = []
        self.requestIndexQueue = []
        self.cache = [{}, {}, {}]
        self.contents = [{}, {}, {}]

        self.manager = QtNetwork.QNetworkAccessManager()
        self.manager.finished.connect(self.networkReply)

        self.volumeSlider.volumeChanged.connect(self.setVolume)

        self.referenceTimer = QtCore.QTimer(interval=10000, timeout=self.seekSlider.updateLabelPositions)
        self.referenceTimer.start()
        self.playlistRequestTimer = QtCore.QTimer(singleShot=True, interval=9000, timeout=self.loadPlaylist)
        self.timeStampTimer = QtCore.QTimer(interval=1000, timeout=self.updateTimeStamp)

        self.recordModel = RecordModel(self)
        self.recordTree.setModel(self.recordModel)
        self.recordTree.setItemDelegateForColumn(3, DurationDelegate())
        self.loadRecordings()

        self.resize(self.width(), self.sizeHint().height())

        self.toggleRecBtn.setIcon(QtGui.QIcon('record.svg'))
        self.floatRecBtn.setIcon(
            self.style().standardIcon(QtWidgets.QStyle.SP_TitleBarNormalButton, None, self))

        showRecordings = self.settings.value('showRecordings', True, type=bool)
        floatRecordings = self.settings.value('floatRecordings', False, type=bool)
        showRecordDock = showRecordings and floatRecordings

        self.recordDock = RecordDock(self, showRecordDock)
        self.recordDock.installEventFilter(self)

        if showRecordDock and not self.settings.contains('recordDockGeo'):
            QtCore.QTimer.singleShot(0, lambda: self.recordDock.adjustSize)

        self.toggleRecBtn.setChecked(showRecordings)
        self.floatRecBtn.setVisible(showRecordings)
        if floatRecordings:
            self.recordDock.setWidget(self.recordTree)
            self.floatRecBtn.setChecked(True)
        else:
            self.recordTree.setVisible(showRecordings)
            self.floatRecBtn.setChecked(False)

        self.toggleRecBtn.toggled.connect(self.toggleRecordings)
        self.floatRecBtn.toggled.connect(self.setFloatRecordings)

        self.recordDock.closed.connect(lambda: self.toggleRecBtn.setChecked(False))
        self.recordDock.unfloat.connect(lambda: self.floatRecBtn.setChecked(False))
        self.recordDockWasVisible = self.recordDock.isVisible()

        self.restoreGeometry(self.settings.value('geometry', type=QtCore.QByteArray))

        self.lastRadio = -1
        lastRadio = self.settings.value('lastRadio', defaultRadio, type=int)

        self.player = Player(self)
        self.player.request.connect(self.requestIndex)

        self._volume = self.settings.value('volume', 100, type=int)
        self.volumeSlider.setVolume(self._volume)
        self.setRadio(lastRadio)

        self.playToggleBtn.installEventFilter(self)

    def useTrayIcon(self):
        return self.settings.value('trayIcon', True, bool)

    def adjustRecordDock(self):
        if not self.recordDock.isVisible():
            QtCore.QTimer.singleShot(0, self.adjustRecordDock)
            return
        geo = self.recordDock.geometry()
        screens = QtWidgets.QApplication.screens()
        for screen in screens:
            if geo.intersects(screen.availableGeometry().adjusted(2, 2, -2, -2)):
                return
        screenGeo = screens[0].availableGeometry()
        if geo.left() > screenGeo.right() - 2:
            geo.moveRight(screenGeo.right())
        elif geo.right() < screenGeo.left() + 2:
            geo.moveLeft(screenGeo.left())
        if geo.top() > screenGeo.bottom() - 2:
            geo.moveBottom(screenGeo.bottom())
        elif geo.bottom() < screenGeo.top() + 2:
            geo.moveTop(screen.top())
        self.recordDock.setGeometry(geo)

    def hideToTray(self):
        self.recordDockWasVisible = self.recordDock.isVisible()
        self.hide()
        self.recordDock.hide()

    def trayClicked(self, reason):
        if reason == self.trayIcon.Trigger:
            if self.isVisible():
                self.recordDockWasVisible = self.recordDock.isVisible()
            self.setVisible(not self.isVisible())
            if self.isVisible() and self.recordDockWasVisible:
                self.recordDock.show()
            elif not self.isVisible():
                self.recordDock.hide()

    def setFloatRecordings(self, floating):
        self.settings.setValue('floatRecordings', floating)
        if floating:
            preHeight = self.height()
            self.recordDock.setWidget(self.recordTree)
            newHeight = preHeight - self.recordTree.height() - self.mainLayout.verticalSpacing()
            self.setFixedHeight(newHeight)
            self.recordDock.show()
        else:
            self.mainLayout.addWidget(self.recordTree)
            self.recordDock.hide()
            self.setFixedHeight(16777215)
            QtWidgets.QApplication.processEvents()
            self.resize(self.width(), self.sizeHint().height())

    def toggleRecordings(self, show):
        self.settings.setValue('showRecordings', show)
        self.floatRecBtn.setVisible(show)
        if self.recordTree.parent() != self.centralWidget():
            self.recordDock.setVisible(show)
        else:
            if show:
                self.setMaximumHeight(16777215)
                self.recordTree.show()
                self.resize(self.width(), self.sizeHint().height())
            else:
                preHeight = self.height()
                self.recordTree.hide()
                newHeight = preHeight - self.recordTree.height() - self.mainLayout.verticalSpacing()
                self.setFixedHeight(newHeight)
                self.resize(self.width(), newHeight)

    def loadRecordings(self):
#        from random import randrange
##        locale = QtCore.QLocale()
#        self.recordModel.clear()
#        self.recordModel.setHorizontalHeaderLabels(['Network', 'Start', 'End', 'Duration'])
#        for radio, title in enumerate(radioTitles):
#            radioItem = QtGui.QStandardItem(title)
#            radioItem.setIcon(self.radioIcons[radio])
#            self.recordModel.appendRow(radioItem)
#            items = randrange(1, 5)
#            for i in range(items):
#                titleItem = QtGui.QStandardItem('Recording {} {}'.format(i + 1, 'x' * randrange(128)))
#                startItem = QtGui.QStandardItem()
#                start = QtCore.QDateTime.currentDateTime()
#                start = start.addDays(randrange(1, 10))
#                start = start.addSecs(randrange(86400))
##                startItem = QtGui.QStandardItem(locale.toString(start, QtCore.QLocale.ShortFormat))
#                startItem.setData(start, QtCore.Qt.DisplayRole)
#                duration = randrange(120, 7200)
##                endItem = QtGui.QStandardItem(locale.toString(start.addSecs(duration), QtCore.QLocale.ShortFormat))
#                endItem = QtGui.QStandardItem()
#                endItem.setData(start.addSecs(duration), QtCore.Qt.DisplayRole)
#                m, s = divmod(duration, 60)
#                h, m = divmod(m, 60)
##                durationItem = QtGui.QStandardItem(QtCore.QTime(h, m, s).toString('HH:mm:ss'))
#                durationItem = QtGui.QStandardItem()
#                durationItem.setData(QtCore.QTime(h, m, s).toString('HH:mm:ss'), QtCore.Qt.DisplayRole)
#                subItems = [titleItem, startItem, endItem, durationItem]
#                for item in subItems[1:]:
#                    item.setFlags(item.flags() & ~ QtCore.Qt.ItemIsEditable)
#                radioItem.appendRow(subItems)
        self.recordTree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
#        self.recordTree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
#        for c in range(1, self.recordModel.columnCount()):
#            self.recordTree.header().setSectionResizeMode(c, QtWidgets.QHeaderView.ResizeToContents)
        self.recordTree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.recordTree.header().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.recordTree.header().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.recordTree.expandAll()

    def updateTimeStamp(self):
        if self.timeEdit.hasFocus():
            return
        if self.liveBtn.isDown():
            self.timeEdit.setTime(self.timeReference())

    def volume(self):
        return self._volume

    def setVolume(self, volume):
        self._volume = max(0, min(volume, 100))
        self.player.setVolume(self._volume)
        self.volumeSlider.setVolume(self._volume)
        self.settings.setValue('volume', self._volume)

    def seek(self, value):
        self.liveBtn.setDown(value == self.seekSlider.maximum() and self.playToggleBtn.isChecked())

    def togglePlay(self, play):
        if play:
            self.loadPlaylist()
            self.playlistRequestTimer.start()
        else:
            self.player.pause()
        if self.seekSlider.value() == self.seekSlider.maximum():
            self.liveBtn.setDown(play)

    def goLive(self):
        self.seekSlider.setValue(self.seekSlider.maximum())
        self.playToggleBtn.setChecked(True)

    def setRadio(self, radio=None, state=True):
        if not state:
            return
        self.setWindowTitle(u'RSI - {}'.format(radioTitles[self.radioGroup.checkedId()]))
        self.recordDock.setWindowTitle(u'RSI - Recordings'.format(self.windowTitle()))

        if isinstance(radio, QtWidgets.QAbstractButton) or radio is None:
            radio = self.radioGroup.checkedId()
            radioBtn = self.radioGroup.button(radio)
        else:
            if isinstance(radio, int):
                radioBtn = self.radioGroup.button(radio)
            else:
                radioBtn = self.rete1Btn
        self.player.setRadio(radio)
        if not self.settings.value('useDefaultRadio', type=bool):
            self.settings.setValue('lastRadio', radio)
        radioBtn.setChecked(True)

        icon = self.radioIcons[radio]
        self.trayIcon.setIcon(icon)
        self.setWindowIcon(icon)

        if self.lastRadio < 0 or self.lastRadio == radio:
            self.lastRadio = radio
            print('returnoooo', self.lastRadio, radio)
            return
        self.lastRadio = radio
        if self.player.currentState in (self.player.ActiveState, self.player.SuspendedState):
            self.player.stop()
            if self.player.currentState == self.player.ActiveState:
                self.loadPlaylist()
#        self.loadPlaylist()

    def loadPlaylist(self):
        radio = self.radioGroup.checkedId()
        url = baseUrl.format(radioNames[radio]) + playlistFile
        req = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
        self.manager.post(req, QtCore.QByteArray())
        if self.liveBtn.isDown():
            self.playlistRequestTimer.start()

    def requestIndex(self, index):
        if not index in self.cache[self.lastRadio]:
            print('file non in cache')
            urlPath = self.contents[self.lastRadio].get(index)
            if not urlPath:
                print('file non in playlist')
                self.loadPlaylist()
                self.requestIndexQueue.insert(0, index)
            else:
                print('file da scaricare')
                self.queue.append(urlPath)
                req = QtNetwork.QNetworkRequest(QtCore.QUrl(urlPath))
                self.manager.post(req, QtCore.QByteArray())

    def networkReply(self, reply):
        if reply.error() != QtNetwork.QNetworkReply.NoError:
            if QtNetwork.QNetworkReply.TimeoutError:
#                print('timeout error!!!')
                self.manager.post(QtNetwork.QNetworkRequest(reply.url()), QtCore.QByteArray())
                return
        fileName = reply.url().fileName()
        url = reply.url().toString()
        data = bytes((reply.readAll()))
#        contents = [r for r in data.split(b'\n') if r.strip() and not r.lstrip().startswith(b'#')]
        for radio, radioName in enumerate(radioNames):
            if radioName in url:
                break
        if url.endswith(playlistFile):
            print('playlist ricevuta')
            contents = [r.decode('utf-8') for r in data.split(b'\n') if r.strip() and not r.lstrip().startswith(b'#')]
            if self.liveBtn.isDown():
                reordered = contents[-3:] + contents[-6:-3]
                for fileName in reordered:
    #                remoteFileName = f.decode('utf-8')
                    filePath = self.cacheDirs[radio] + fileName
                    if not QtCore.QFile.exists(filePath):
                        urlPath = baseUrl.format(radioName) + fileName
                        if not urlPath in self.queue:
                            self.queue.append(urlPath)
                            req = QtNetwork.QNetworkRequest(QtCore.QUrl(urlPath))
                            self.manager.post(req, QtCore.QByteArray())
                if self.player.currentState != self.player.ActiveState:
                    QtCore.QTimer.singleShot(1000, self.loadPlaylist)
            contentDict = {}
            for fileName in contents:
                index = int(findIndex.findall(fileName)[-1])
                contentDict[index] = baseUrl.format(radioName) + fileName
            self.contents[radio].update(contentDict)
            toRemove = []
            for index in self.requestIndexQueue:
                if not index in self.contents[radio]:
                    print('index {} non esiste ancora'.format(index))
                    if not self.playlistRequestTimer.isActive():
                        self.loadPlaylist()
                    continue
                toRemove.append(index)
                urlPath = self.contents[radio][index]
                if not urlPath in self.queue:
                    self.queue.append(urlPath)
                    req = QtNetwork.QNetworkRequest(QtCore.QUrl(urlPath))
                    self.manager.post(req, QtCore.QByteArray())
            while toRemove:
                self.requestIndexQueue.remove(toRemove.pop())
        else:
            if not url in self.queue:
                print('wtf?', url)
                return
            self.queue.remove(url)
            filePath = QtCore.QDir(self.cacheDirs[radio]).absoluteFilePath(fileName)
            f = QtCore.QFile(filePath)
            f.open(f.WriteOnly)
            f.write(data)
            f.close()
            indexStr = findIndex.findall(fileName)[-1]
            index = int(indexStr)
            if self.player.currentState != self.player.ActiveState and self.liveBtn.isDown():
                pre = fileName.index(indexStr)
                self.player.setFileNameTemplate(fileName[:pre], fileName[pre + len(indexStr):])
                self.player.start(index)
                self.timeStampTimer.start()
                self.updateTimeStamp()
            self.cache[radio][index] = fileName
#        print('reply!', url.endswith(playlistFile))

    def timeReference(self):
        return QtCore.QTime.currentTime().addSecs(-10)

    def restoreRecordDockGeometry(self):
        if not self.recordDockShown:
            self.recordDockShown = True
            recordDockGeo = self.settings.value('recordDockGeo', type=QtCore.QByteArray)
            if recordDockGeo:
                self.recordDock.restoreGeometry(recordDockGeo)
                self.adjustRecordDock()
                return True
            self.adjustRecordDock()
        return False

    def stepVolume(self, amount):
        self.setVolume(self.volume() + amount)

    def volumeUp(self):
        self.stepVolume(VolumeStep)

    def volumeDown(self):
        self.stepVolume(-VolumeStep)

    def eventFilter(self, source, event):
        if source == self.recordDock:
            if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Move) and source.isVisible():
                return self.restoreRecordDockGeometry()
            elif event.type() == QtCore.QEvent.Show:
                return self.restoreRecordDockGeometry()
            elif event.type() == QtCore.QEvent.Hide:
                self.settings.setValue('recordDockGeo', self.recordDock.saveGeometry())
        elif source == self.playToggleBtn:
            # maybe set NoFocus to everything?
            if event.type() == QtCore.QEvent.KeyPress:
                if event.key() == QtCore.Qt.Key_Up:
                    self.volumeUp()
                    return True
                elif event.key() == QtCore.Qt.Key_Down:
                    self.volumeDown()
                    return True
                elif event.key() == QtCore.Qt.Key_Left:
                    #self.seekBack()
                    pass
                elif event.key() == QtCore.Qt.Key_Right:
                    #self.seekForward()
                    pass
                elif not event.key() in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
                    return False
        return super().eventFilter(source, event)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_M:
            if self.volume():
                oldVolume = self.volumeSlider.volume()
                self.setVolume(0)
                self.volumeSlider.oldVolume = oldVolume
            else:
                self.setVolume(self.volumeSlider.oldVolume if self.volumeSlider.oldVolume else 10)
        else:
            super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.shown:
            self.shown = True
            if self.recordTree.parent() != self.centralWidget():
                self.setFixedHeight(self.sizeHint().height())
#            self.recordTree.resizeColumnToContentsm

    def closeEvent(self, event):
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('recordDockGeo', self.recordDock.saveGeometry())
        if not self.settings.contains('trayIcon') or self.settings.value('closeToTray', False, type=bool):
            msgBox = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Question, 
                'Close RSI Play?', 
                'Do you want to keep RSIPlay running?', 
                parent=self
                )
            hideToTrayBtn = msgBox.addButton(
                'Hide to tray', msgBox.AcceptRole)
            quitOnCloseBtn = msgBox.addButton(
                'Quit', msgBox.AcceptRole)
            cancelBtn = msgBox.addButton(
                'Cancel', msgBox.RejectRole)
            if not msgBox.exec_() or msgBox.clickedButton() == cancelBtn:
                event.ignore()
                return
            if msgBox.clickedButton() == hideToTrayBtn:
                self.settings.setValue('closeToTray', True)
            self.settings.setValue('trayIcon', True)
        if (self.settings.value('trayIcon', True, type=bool) and
            (self.settings.value('closeToTray', False, type=bool))):
                QtWidgets.QApplication.setQuitOnLastWindowClosed(False)
                self.hideToTray()
        elif self.recordDock.isVisible():
            self.recordDock.close()
#            QtWidgets.QApplication.setQuitOnLastWindowClosed(True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.seekSlider.updateLabelPositions()
        self.referenceTimer.start()


if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    app.setOrganizationName('jidesk')
    app.setApplicationName('PlayRSI')
    styles = [s.lower() for s in QtWidgets.QStyleFactory.keys()]
    if 'oxygen' in styles:
        style = QtWidgets.QStyleFactory.create('oxygen')
        app.setStyle(style)
        if 'breeze' in styles:
            app.setPalette(QtWidgets.QStyleFactory.create('breeze').standardPalette())
#    oxygen = QtWidgets.QStyleFactory.create('oxygen')
#    breeze = QtWidgets.QStyleFactory.create('oxygen')
#    app.setStyle(oxygen)
#    app.setPalette(breeze.standardPalette())
    playerWindow = RsiPlayer()
    playerWindow.show()
    sys.exit(app.exec_())
