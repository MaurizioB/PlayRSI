#!/usr/bin/env python3

import os
import re
import json
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

FindIndexRegEx = re.compile('\d+')
BaseStreamUrl = 'https://lsaplus.swisstxt.ch/audio/{}_96.stream/'
PlaylistFileName = 'chunklist_DVR.m3u8'
SongLogBaseUrl = 'https://www.rsi.ch/play/radio/songlog/'

ShortRadioNames = 'uno', 'due', 'tre'
RadioNames = []
RadioTitles = []
SongLogUrls = []
for n in ShortRadioNames:
    RadioNames.append('rete{}'.format(n))
    RadioTitles.append('Rete{}'.format(n.title()))
    SongLogUrls.append('{}rete-{}'.format(SongLogBaseUrl, n))
#    RadioNames = tuple('rete{}'.format(n) for n in ShortRadioNames)
#    RadioTitles = tuple('Rete{}'.format(n.title()) for n in ShortRadioNames)
#    SongLogUrls = ['{}rete-{}/'.format(SongLogBaseUrl, ShortRadioNames[radio])]

IconSizes = [QtCore.QSize(s, s) for s in (16, 20, 22, 24, 32, 64, 128, 256)]

StartRole = QtCore.Qt.UserRole + 1000
EndRole = StartRole + 1


class Player(QtCore.QObject):
    ActiveState, SuspendedState, StoppedState, IdleState = range(4)
    currentStateChanged = QtCore.pyqtSignal(int)
    request = QtCore.pyqtSignal(int)

    def __init__(self, parent):
        super().__init__(parent)
        self.pyaudio = pyaudio.PyAudio()
        self.stream = None
        self.nextData = None
        self._currentState = self.StoppedState
        self._volume = 1
#        self.curve = QtCore.QEasingCurve(QtCore.QEasingCurve.InCubic)

    @property
    def currentState(self):
        return self._currentState

    @currentState.setter
    def currentState(self, state):
        if state == self._currentState:
            return
        self._currentState = state
        self.currentStateChanged.emit(state)

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

        if self.currentState == self.SuspendedState and index == self.currentIndex:
            self.stream.start_stream()
            self.currentState = self.ActiveState
        else:
            self.currentIndex = index
            self.currentData = self.getData(index, radio)

            self.bytePos = 0
            self.stream.start_stream()
            self.currentState = self.ActiveState
            self.request.emit(index + 1)
            self.overlapping = False

    def pause(self):
        if self.stream:
            self.stream.stop_stream()
            self.currentState = self.SuspendedState

    def resume(self):
        if self.stream:
            self.stream.start_stream()
            self.currentState = self.ActiveState

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
            if not pos in rect and QtWidgets.QApplication.mouseButtons():
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
        screenPos = self.mapToGlobal(QtCore.QPoint())
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), self.toolTip(), self, self.rect().translated(-screenPos))
        event.accept()

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
    cacheBackground = QtGui.QColor(32, 32, 32, 96)

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
        self.actionTriggered = self.slider.actionTriggered
        self.sliderReleased = self.slider.sliderReleased
        self.sliderMoved = self.slider.sliderMoved
        self.slider.installEventFilter(self)
        self.maximum = self.slider.maximum
        self.value = self.slider.value
        self.setValue = self.slider.setValue
        self.slider.setMaximum(2160)
        self.oldValue = self.maximum()
        self.setValue(self.maximum())
        self.slider.setMouseTracking(True)

        self.sliderOption = QtWidgets.QStyleOptionSlider()

        self.setFixedHeight(self.topMargin + self.slider.minimumSizeHint().height() + 2)

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
        self.slider.setGeometry(self.rect().adjusted(0, self.topMargin, 0, -2))
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
#        print(self.parent(), self.window().timeStamps)

        timeStamps = self.window().timeStamps[self.window().lastRadio]
        if timeStamps:
            cacheData = self.window().cache[self.window().lastRadio]
            cacheSize = (self.maxTick - self.minTick) / 2160
            cacheRect = QtCore.QRectF(0, 0, cacheSize, self.topMargin)
            qp.save()
            qp.setRenderHints(qp.Antialiasing)
            qp.setPen(QtCore.Qt.NoPen)
            qp.setBrush(self.cacheBackground)
            qp.translate(self.maxTick - cacheSize, 0)
            c = 0
            for length, index in reversed(timeStamps):
                if index in cacheData:
                    qp.drawRect(cacheRect)
                qp.translate(-cacheSize, 0)
                c += 1
                if c > 2160:
                    break
            qp.restore()

        if self.hourSize >= 48:
            qp.save()
            y = self.topMargin * .6
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
            qp.drawText(textRect, QtCore.Qt.AlignCenter, timeStr)
            hour += 1
            hour %= 24
        opt = QtWidgets.QStyleOptionSlider()
        self.slider.initStyleOption(opt)
        grooveRect = self.slider.style().subControlRect(QtWidgets.QStyle.CC_Slider, 
            opt, QtWidgets.QStyle.SC_SliderGroove, self.slider)

        if self.hourTicks[0] > grooveRect.left() + textRect.width() + 4:
            timeStr = self.window().timeReference().addSecs(-21600).toString('HH:mm')
            textRect = fm.boundingRect(hourRect.translated(grooveRect.left(), 0), 
                QtCore.Qt.AlignLeft|QtCore.Qt.AlignTop, timeStr).adjusted(0, 0, 2, 0)
            qp.save()
            qp.setPen(QtCore.Qt.NoPen)
            qp.setBrush(self.hourBackground)
            qp.drawRoundedRect(textRect, 2, 2)
            qp.restore()
            qp.drawText(textRect, QtCore.Qt.AlignCenter, timeStr)


class TrayIcon(QtWidgets.QSystemTrayIcon):
    wheel = QtCore.pyqtSignal(int)
    def event(self, event):
        if event.type() == QtCore.QEvent.Wheel:
            self.wheel.emit(event.angleDelta().y())
        return super().event(event)


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
        for radio, (radioName, radioTitle) in enumerate(zip(RadioNames, RadioTitles)):
            radioItem = QtGui.QStandardItem(radioTitle)
            radioItem.setIcon(QtGui.QIcon('{}.png'.format(radioName)))
            self.appendRow(radioItem)

            randomString = 'randomtext ' * 100
            for r in range(randrange(1, 5)):
                recordItem = QtGui.QStandardItem('Recording {} [{}]'.format(r + 1, randomString[:randrange(128)]))
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
        


class ExpandButton(QtWidgets.QToolButton):
    arrowSize = None
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def resizeEvent(self, event):
        if self.arrowSize is None:
            opt = QtWidgets.QStyleOptionToolButton()
            self.initStyleOption(opt)
            size = self.style().pixelMetric(QtWidgets.QStyle.PM_ButtonIconSize, opt, self)
            resSize = size / 4
            self.__class__.arrowSize = size
            rect = QtCore.QRectF(0, 0, size, size)
            rect.adjust(resSize, resSize, -resSize, -resSize)
            center = rect.center()

            self.__class__.bottomPath = bottomPath = QtGui.QPainterPath()
            bottomPath.moveTo(rect.topLeft())
            bottomPath.lineTo(rect.topRight())
            bottomPath.lineTo(center.x(), rect.bottom())
            bottomPath.translate(-bottomPath.boundingRect().center())
            bottomPath.closeSubpath()

            self.__class__.topPath = topPath = QtGui.QPainterPath()
            topPath.moveTo(rect.bottomLeft())
            topPath.lineTo(rect.bottomRight())
            topPath.lineTo(center.x(), center.y() - resSize)
            topPath.translate(-topPath.boundingRect().center())
            topPath.closeSubpath()

    def paintEvent(self, event):
        super().paintEvent(event)
        qp = QtGui.QPainter(self)
        qp.setRenderHints(qp.Antialiasing)
        qp.translate(QtCore.QRectF(self.rect()).center())
        qp.setPen(QtCore.Qt.NoPen)
        qp.setBrush(self.palette().color(QtGui.QPalette.Text))
        qp.drawPath(self.bottomPath if self.isChecked() else self.topPath)


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        uic.loadUi('settings.ui', self)
        self.settings = QtCore.QSettings()
        self.defaultRadioCombo.addItems(RadioTitles)

    def exec_(self):
        if self.settings.value('useDefaultRadio', False, type=bool):
            self.defaultRadioRadio.setChecked(True)
        else:
            self.lastRadioRadio.setChecked(True)
        self.defaultRadioCombo.setCurrentIndex(self.settings.value('lastRadio', 0, type=int))
        self.playOnStartCombo.setCurrentIndex(max(-1, self.settings.value('playOnStart', 1, type=int)) + 1)

        self.trayIconBox.setChecked(self.settings.value('trayIcon', True, type=bool))
        self.closeToTrayChk.setChecked(self.settings.value('closeToTray', True, type=bool))
        self.startToTrayChk.setChecked(self.settings.value('startToTray', False, type=bool))

        self.storeGeometryChk.setChecked(self.settings.value('storeGeometry', True, type=bool))
        self.askToQuitChk.setChecked(self.settings.value('askToQuit', True, type=bool))
        if not super().exec_():
            return

        useLastRadio = self.lastRadioRadio.isChecked()
        self.settings.setValue('useDefaultRadio', not useLastRadio)
        if not useLastRadio:
            self.settings.setValue('lastRadio', self.defaultRadioCombo.currentIndex())
        self.settings.setValue('playOnStart', self.playOnStartCombo.currentIndex() - 1)

        self.settings.setValue('trayIcon', self.trayIconBox.isChecked())
        self.settings.setValue('closeToTray', self.closeToTrayChk.isChecked())
        self.settings.setValue('startToTray', self.startToTrayChk.isChecked())

        storeGeometry = self.storeGeometryChk.isChecked()
        self.settings.setValue('storeGeometry', storeGeometry)
        if storeGeometry:
            self.settings.setValue('geometry', self.parent().saveGeometry())
        else:
            self.settings.remove('geometry')
        self.settings.setValue('askToQuit', self.askToQuitChk.isChecked())


class NowPlaying(QtWidgets.QTextBrowser):
    refreshRequested = QtCore.pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setOpenLinks(False)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.refreshBtn = QtWidgets.QPushButton(self)
        self.refreshBtn.setFocusPolicy(QtCore.Qt.NoFocus)
        self.refreshBtn.setIcon(QtGui.QIcon('refresh.svg'))
        self.refreshBtn.hide()
        self.refreshBtn.clicked.connect(self.refreshRequested)
        self.document().setDefaultStyleSheet('''
            body {{
                font-size: {fontSize}px;
                background: white;
            }}
            a {{
                text-decoration: none;
                color: rgb(64, 64, 64); 
            }}
        '''.format(
            fontSize = int(self.font().pointSize() * 1.5)
            ))

    def enterEvent(self, event):
        self.refreshBtn.show()

    def leaveEvent(self, event):
        self.refreshBtn.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        geo = QtCore.QRect(QtCore.QPoint(), self.refreshBtn.minimumSizeHint())
        geo.moveTopRight(self.viewport().geometry().topRight() + QtCore.QPoint(-2, 2))
        self.refreshBtn.setGeometry(geo)


class RsiPlayer(QtWidgets.QMainWindow):
    shown = False
#    recordDockShown = False

    def __init__(self):
        super().__init__()
        uic.loadUi('player.ui', self)

        self.settings = QtCore.QSettings()
#        defaultRadio = self.settings.value('defaultRadio', 0, type=int)
        cacheDirs = QtCore.QStandardPaths.standardLocations(
            QtCore.QStandardPaths.AppDataLocation)
        self.cacheDirs = []
        try:
            for cacheDir in cacheDirs:
                cd = QtCore.QFileInfo(cacheDir)
                if not cd.exists():
                    assert QtCore.QDir().mkpath(cd.absoluteFilePath())
                rootDir = QtCore.QDir(cd.absoluteFilePath())
                for radioDir in RadioNames:
                    self.cacheDirs.append(rootDir.absoluteFilePath(radioDir))
                    if not rootDir.exists(radioDir):
                        rootDir.mkpath(radioDir)
                if cd.isWritable():
                    break
        except Exception as e:
            print('TODO create temp dir?', e)

        self.radioPixmaps = []
        self.radioIcons = []
        self.windowIcons = []

        for radio, radioName in enumerate(RadioNames, 1):
            btn = getattr(self, 'rete{}Btn'.format(radio))
            pixmap = QtGui.QPixmap('{}.png'.format(radioName))
            btn.buttonPixmap = pixmap
            self.radioPixmaps.append(pixmap)
            self.radioIcons.append(QtGui.QIcon(pixmap))
            windowIcon = QtGui.QIcon()
            for size in reversed(IconSizes):
                pm = QtGui.QPixmap(size)
                pm.fill(QtCore.Qt.transparent)
                qp = QtGui.QPainter(pm)
                qp.setRenderHints(qp.SmoothPixmapTransform)
                scaled = pixmap.scaled(size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                r = scaled.rect()
                r.moveCenter(pm.rect().center())
                qp.drawPixmap(r, scaled)
                qp.end()
                windowIcon.addPixmap(pm)
            self.windowIcons.append(windowIcon)

        self.showIcons = [
            QtGui.QIcon('hide.svg'), 
            QtGui.QIcon('show.svg')
        ]

        self.trayIcon = TrayIcon(self.radioIcons[0])
        if self.useTrayIcon():
            self.trayIcon.show()
        self.trayIcon.activated.connect(self.trayClicked)
        self.trayIcon.wheel.connect(lambda v: self.volumeUp() if v > 0 else self.volumeDown())

        self.playCache = {r:{} for r in range(3)}

        self.radioGroup.setId(self.rete1Btn, 0)
        self.radioGroup.setId(self.rete2Btn, 1)
        self.radioGroup.setId(self.rete3Btn, 2)
        self.radioGroup.buttonToggled[QtWidgets.QAbstractButton, bool].connect(self.setRadio)

        self.settingsBtn.setIcon(QtGui.QIcon('settings.svg'))
        self.settingsBtn.setFixedSize(40, 40)

#        quitAction = (QtWidgets.QAction(QtGui.QIcon.fromTheme('application-exit)'), 
#                'Quit', self))
#            quitAction.triggered.connect(QtWidgets.QApplication.quit)
#        self.mainMenu.addAction(quitAction)

        self.playIcons = (QtGui.QIcon('pause.png'), QtGui.QIcon('play.png'))
        self.whitePlayIcons = (QtGui.QPixmap('pause-white.png'), QtGui.QPixmap('play-white.png'))
        self.playToggleBtn.setIcon(self.playIcons[1])
        self.playToggleBtn.toggled.connect(self.togglePlay)
#        self.playToggleBtn.setFixedHeight(self.seekSlider.minimumHeight())

        self.seekSlider.valueChanged.connect(self.seekSliderMoved)
        self.seekSlider.sliderReleased.connect(self.seek)
        self.delaySeekTimer = QtCore.QTimer(singleShot=True, interval=250, timeout=self.seek)
        self.seekSlider.actionTriggered.connect(self.seekTriggered)

        self.liveBtn.clicked.connect(self.goLive)

        self.queue = []
        self.requestIndexQueue = []
        self.cache = [{}, {}, {}]
        self.contents = [{}, {}, {}]
        self.songLogs = [[], [], []]
        self.timeStamps = [[], [], []]
        self.nextToPlay = None

        self.manager = QtNetwork.QNetworkAccessManager()
        self.manager.finished.connect(self.networkReply)

        self.volumeSlider.volumeChanged.connect(self.setVolume)

        self.referenceTimer = QtCore.QTimer(interval=10000, timeout=self.seekSlider.updateLabelPositions)
        self.referenceTimer.start()
        self.playlistRequestTimer = QtCore.QTimer(singleShot=True, interval=9000, timeout=self.loadPlaylist)
        self.songLogRequestElapsed = QtCore.QElapsedTimer()
        self.songLogRequestElapsed.start()
        self.timeStampTimer = QtCore.QTimer(interval=1000, timeout=self.updateTimeStamp)

        self.panel = QtWidgets.QTabWidget()
        self.mainLayout.addWidget(self.panel)
        self.panel.setFocusPolicy(QtCore.Qt.NoFocus)

        self.nowPlaying = NowPlaying()
        self.panel.addTab(self.nowPlaying, QtGui.QIcon('info.svg'), 'No&w playing')
        self.nowPlaying.anchorClicked.connect(self.goToClickedTime)
        self.nowPlaying.refreshRequested.connect(self.requestSongLog)

        self.recordTree = QtWidgets.QTreeView()
        self.recordModel = RecordModel(self)
        self.recordTree.setModel(self.recordModel)
        self.recordTree.setEditTriggers(self.recordTree.NoEditTriggers)
        self.recordTree.header().setStretchLastSection(False)
        self.recordTree.header().setDefaultAlignment(QtCore.Qt.AlignCenter)
        self.recordTree.setItemDelegateForColumn(3, DurationDelegate())
        self.loadRecordings()

        self.panel.addTab(self.recordTree, QtGui.QIcon('record.svg'), '&Recordings')

        self.panel.setVisible(self.settings.value('showPanel', True, type=bool))


#        self.resize(self.width(), self.sizeHint().height())


#        lastRadio = self.settings.value('lastRadio', defaultRadio, type=int)

        self.player = Player(self)
        self.player.request.connect(self.requestIndex)
        self.player.currentStateChanged.connect(self.updateTrayIcon)

        self.lastRadio = -1
        self._volume = self.settings.value('volume', 100, type=int)
        self.volumeSlider.setVolume(self._volume)

        self.setRadio(self.settings.value('lastRadio', 0, type=int))

        self.playToggleBtn.installEventFilter(self)

        self.settingsDialog = SettingsDialog(self)

        self.mainMenu = QtWidgets.QMenu(self)
        self.settingsBtn.clicked.connect(lambda: self.mainMenu.exec_(
            self.settingsBtn.mapToGlobal(self.settingsBtn.rect().bottomLeft())))
        self.showSettingsAction = QtWidgets.QAction(self.settingsBtn.icon(), 'Show settings...', self)
        self.mainMenu.addAction(self.showSettingsAction)
        self.showSettingsAction.triggered.connect(self.showSettings)

        self.trayMenu = QtWidgets.QMenu(self)
        self.trayMenu.setSeparatorsCollapsible(False)
        self.trayMenu.addSection('RSIPlay')
        self.trayMenu.aboutToShow.connect(self.sysTrayMenuShowing)
        self.toggleWindowAction = self.trayMenu.addAction('')
        self.toggleWindowAction.triggered.connect(self.toggleWindow)
        self.togglePlayAction = self.trayMenu.addAction('')
#        self.togglePlayAction.triggered.connect(lambda: (None, self.setRadio(self.lastRadio), self.goLive()))
        self.togglePlayAction.triggered.connect(lambda: self.playToggleBtn.setChecked(not self.playToggleBtn.isChecked()))

        self.trayMenu.addSeparator()

        self.sysTrayRadioGroup = QtWidgets.QActionGroup(self.trayMenu)
        for radio, radioName in enumerate(RadioTitles):
            action = self.trayMenu.addAction(self.windowIcons[radio], radioName)
            action.setCheckable(True)
            action.triggered.connect(lambda _, r=radio: [None, (self.setRadio(r), self.goLive())][_])
            self.sysTrayRadioGroup.addAction(action)
            self.trayMenu.addAction(action)

        self.trayMenu.addSeparator()

        if self.settings.value('playOnStart', -2, type=int) in (-2, 1):
            QtCore.QTimer.singleShot(0, lambda: self.playToggleBtn.setChecked(True))

        quitAction = (QtWidgets.QAction(QtGui.QIcon('quit.svg'), 
                '&Quit', self))
        quitAction.setShortcut(QtGui.QKeySequence.fromString('ctrl+q'))
        quitAction.setShortcutContext(QtCore.Qt.ApplicationShortcut)
#        non funziona?!
        quitAction.triggered.connect(self.quit)

        self.mainMenu.addSeparator()
        self.mainMenu.addAction(quitAction)
        self.trayMenu.addAction(quitAction)
        self.addAction(quitAction)

        self.timeEdit.setDateTime(QtCore.QDateTime.currentDateTime())
        self.timeEdit.installEventFilter(self)

        self.togglePanelBtn.toggled.connect(self.togglePanel)

    def togglePanel(self, show):
        if show:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            QtWidgets.QApplication.processEvents()
            height = self.panel.height()
            self.panel.show()
            self.resize(self.width(), self.height() + height + self.mainLayout.verticalSpacing())
        else:
            height = self.panel.height()
            self.panel.hide()
            QtWidgets.QApplication.processEvents()
            self.setFixedHeight(self.height() - height - self.mainLayout.verticalSpacing())

    def toggleWindow(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()

    def sysTrayMenuShowing(self):
        if self.isVisible():
            self.toggleWindowAction.setText('Hide player')
        else:
            self.toggleWindowAction.setText('Show player')
        self.toggleWindowAction.setIcon(self.showIcons[not self.isVisible()])
        for radio, action in enumerate(self.sysTrayRadioGroup.actions()):
            action.setChecked(self.liveBtn.isDown() and self.lastRadio == radio)
        isPlaying = self.player.currentState == self.player.ActiveState
        self.togglePlayAction.setIcon(self.playIcons[not isPlaying])
        self.togglePlayAction.setText('Pause' if isPlaying else 'Play')
#        if self.player.currentState == self.player.ActiveState:
#            self.togglePlayAction.setIcon(False)
#            self.togglePlayAction.setText('Play')
#        else:
#            self.togglePlayAction.setIcon(True)
#            self.togglePlayAction.setText('Pause')

    def showSettings(self):
        self.settingsDialog.exec_()

    def useTrayIcon(self):
        return self.settings.value('trayIcon', True, bool)

#    def adjustRecordDock(self):
#        if not self.recordDock.isVisible():
#            QtCore.QTimer.singleShot(0, self.adjustRecordDock)
#            return
#        geo = self.recordDock.geometry()
#        screens = QtWidgets.QApplication.screens()
#        for screen in screens:
#            if geo.intersects(screen.availableGeometry().adjusted(2, 2, -2, -2)):
#                return
#        screenGeo = screens[0].availableGeometry()
#        if geo.left() > screenGeo.right() - 2:
#            geo.moveRight(screenGeo.right())
#        elif geo.right() < screenGeo.left() + 2:
#            geo.moveLeft(screenGeo.left())
#        if geo.top() > screenGeo.bottom() - 2:
#            geo.moveBottom(screenGeo.bottom())
#        elif geo.bottom() < screenGeo.top() + 2:
#            geo.moveTop(screen.top())
#        self.recordDock.setGeometry(geo)

    def trayClicked(self, reason):
        if reason == self.trayIcon.Trigger:
            self.toggleWindow()
        elif reason == self.trayIcon.MiddleClick:
            self.playToggleBtn.setChecked(not self.playToggleBtn.isChecked())
        elif reason == self.trayIcon.Context:
            self.trayMenu.exec_(QtGui.QCursor.pos())

    def loadRecordings(self):
        self.recordTree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.recordTree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.recordTree.header().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.recordTree.header().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.recordTree.expandAll()

    def updateTimeStamp(self):
        self.updateTimeLimits()
        if self.timeEdit.hasFocus():
            return
        time = self.timeReference()
        if not self.liveBtn.isDown():
            diff = (self.seekSlider.maximum() - self.seekSlider.value()) * 10
            time = time.addSecs(-diff)
        self.timeEdit.setTime(time)

    def updateTimeLimits(self):
        now = QtCore.QDateTime.currentDateTime()
        self.timeEdit.setMaximumDateTime(now)
        self.timeEdit.setMinimumDateTime(now.addSecs(-21600))
#        if not self.playToggleBtn.isChecked()
#        if self.seekSlider.value() == self.seekSlider

    def volume(self):
        return self._volume

    def setVolume(self, volume):
        self._volume = max(0, min(volume, 100))
        self.player.setVolume(self._volume)
        self.volumeSlider.setVolume(self._volume)
        self.settings.setValue('volume', self._volume)
        if self.lastRadio >= 0:
            self.updateTrayIcon()

    def seekSliderMoved(self, value):
        self.liveBtn.setDown(value == self.seekSlider.maximum() and self.playToggleBtn.isChecked())

    def seekTriggered(self, action):
        if action in (QtWidgets.QSlider.SliderPageStepSub, QtWidgets.QSlider.SliderPageStepAdd):
            self.delaySeekTimer.start()

    def seek(self):
        if self.seekSlider.value() == self.seekSlider.maximum():
            if not self.timeStamps[self.lastRadio]:
                self.loadPlaylist()
                QtCore.QTimer.singleShot(100, self.seek)
            else:
                self.goToIndex(self.timeStamps[self.lastRadio][-1][1])
        else:
            now = QtCore.QTime.currentTime()
            timeIter = iter(reversed(self.timeStamps[self.lastRadio]))
            seekPos = 2160
            sliderPos = self.seekSlider.value()
            while seekPos > sliderPos:
                length, index = next(timeIter)
                now = now.addMSecs(-length)
                seekPos -= 1
            self.goToIndex(index)

    def togglePlay(self, play):
        if play:
            if self.player.currentState == self.player.SuspendedState:
                self.player.resume()
            self.loadPlaylist(requestSongLog=True)
            self.playlistRequestTimer.start()
        else:
            self.player.pause()
            self.timeStampTimer.stop()
        if self.seekSlider.value() == self.seekSlider.maximum():
            self.liveBtn.setDown(play)

    def goLive(self):
        self.seekSlider.setValue(self.seekSlider.maximum())
        self.playToggleBtn.setChecked(True)
        self.seek()

    def setRadio(self, radio=None, state=True):
        if not state:
            return
        self.setWindowTitle(u'RSI - {}'.format(RadioTitles[self.radioGroup.checkedId()]))

        if isinstance(radio, QtWidgets.QAbstractButton) or radio is None:
            radio = self.radioGroup.checkedId()
            radioBtn = self.radioGroup.button(radio)
        else:
            if isinstance(radio, int):
                radioBtn = self.radioGroup.button(radio)
            else:
                radioBtn = self.rete1Btn
        self.player.setRadio(radio)
        if not self.settings.value('useDefaultRadio', False, type=bool):
            self.settings.setValue('lastRadio', radio)
        radioBtn.setChecked(True)

#        self.trayIcon.setIcon(self.radioIcons[radio])
        self.setWindowIcon(self.windowIcons[radio])
        self.requestSongLog(radio)

        if self.lastRadio < 0 or self.lastRadio == radio:
            self.lastRadio = radio
            self.updateTrayIcon()
#            print('returnoooo', self.lastRadio, radio)
            return
        self.lastRadio = radio
        self.updateTrayIcon()
        if self.player.currentState in (self.player.ActiveState, self.player.SuspendedState):
            self.player.stop()
            if self.player.currentState == self.player.ActiveState:
                self.loadPlaylist(requestSongLog=True)
#        self.loadPlaylist()

    def updateTrayIcon(self):
        size = self.trayIcon.geometry().height()
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.transparent)
        rect = pixmap.rect().adjusted(1, 1, -2, -2)
        qp = QtGui.QPainter(pixmap)
#        qp.save()
#        qp.fillRect(pixmap.rect(), QtCore.Qt.green)
        qp.translate(.5, .5)
        qp.setRenderHints(qp.Antialiasing | qp.SmoothPixmapTransform)
#        qp.setPen(QtCore.Qt.darkGray)
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect), 2, 2)
        radioPixmap = self.radioPixmaps[self.lastRadio].scaledToWidth(
            rect.width() - 2, QtCore.Qt.SmoothTransformation)

        playSize = max(5, rect.width() / 3)
        playRect = QtCore.QRect(0, 0, playSize, playSize)
        playRect.moveBottomLeft(rect.bottomLeft() + QtCore.QPoint(1, -1))

        qp.save()
        qp.setClipPath(path)
        qp.fillRect(rect, QtGui.QColor(0, 0, 0, 128))
        volumeWidth = rect.width() - playRect.width() - 2
        diff = volumeWidth * (100 - self.volume()) / 100
        qp.fillRect(rect.adjusted(playRect.width() + 2, radioPixmap.height() + max(2, radioPixmap.height() * .1), -diff, -1), QtGui.QColor(128, 128, 128, 127))
        qp.restore()

        playIcon = self.whitePlayIcons[self.player.currentState == self.player.ActiveState]
        qp.drawPixmap(playRect, playIcon, playIcon.rect())

        qp.setPen(QtCore.Qt.lightGray)
        qp.drawPath(path)
        qp.drawPixmap(rect.topLeft() + QtCore.QPoint(1, 0), radioPixmap)
#        qp.drawRoundedRect(rect, 2, 2)
        qp.end()
        self.trayIcon.setIcon(QtGui.QIcon(pixmap))

        if self.player.currentState == self.player.ActiveState:
            state = '\nplaying '
            if self.volume():
                state += ' (volume {}%)'.format(self.volume())
            else:
                state += ' (muted)'
        else:
            state = ''
        
        toolTip = 'RSI - {radio}{state}'.format(
            radio = RadioTitles[self.lastRadio], 
            state = state
            )
        if toolTip != self.trayIcon.toolTip():
            self.trayIcon.setToolTip(toolTip)
            if not self.isVisible():
                QtWidgets.QToolTip.showText(self.trayIcon.geometry().center(), toolTip)

    headers = {}
    for k, v in QtNetwork.QNetworkRequest.__dict__.items():
        if isinstance(v, QtNetwork.QNetworkRequest.KnownHeaders):
            headers[v] = k

    def requestSongLog(self, radio=None):
        print('chiedo songlog')
        if radio is None:
            radio = self.lastRadio
        req = QtNetwork.QNetworkRequest(QtCore.QUrl(SongLogUrls[radio]))
        self.manager.get(req)
        self.songLogRequestElapsed.start()

    def loadPlaylist(self, requestSongLog=False):
        print('loadPlaylist')
        radio = self.radioGroup.checkedId()
        url = BaseStreamUrl.format(RadioNames[radio]) + PlaylistFileName
        req = QtNetwork.QNetworkRequest(QtCore.QUrl(url))
#        self.manager.post(req, QtCore.QByteArray())
        self.manager.get(req)
        if self.liveBtn.isDown():
            self.playlistRequestTimer.start()
#        logRequestUrl = '{}rete-{}/'.format(SongLogBaseUrl, ShortRadioNames[radio])
#        logRequestUrl = 'https://www.rsi.ch/play/radio/songlog/rete-due'
        if requestSongLog or self.songLogRequestElapsed.elapsed() > 60000:
            self.requestSongLog(radio)
#        req.setRawHeader(QtCore.QByteArray('User-Agent', 'MyAppName/1.0 (Nokia; Qt)')
#        for h, n in self.headers.items():
#            print('request header', n, req.header(h))
#        print('chiedo song list?', url, logRequestUrl, self.manager.get(req))

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
                self.manager.get(req)

    def networkReply(self, reply):
        if reply.error() != QtNetwork.QNetworkReply.NoError:
            if reply.error() == QtNetwork.QNetworkReply.TimeoutError:
#                print('timeout error!!!', reply.url().toString())
#                if reply.url().toString().startswith(SongLogBaseUrl):
#                    return
                self.manager.get(QtNetwork.QNetworkRequest(reply.url()))
                return
            else:
                print('errore?!', reply.error(), '"{}"'.format(reply.url().toString()))
                print(reply.readAll())
                return
        fileName = reply.url().fileName()
        url = reply.url().toString()
        data = bytes((reply.readAll()))
#        contents = [r for r in data.split(b'\n') if r.strip() and not r.lstrip().startswith(b'#')]
        for radio, radioName in enumerate(RadioNames):
            if radioName in url:
                break
#        print('url received', url)
        if url.endswith(PlaylistFileName):
            print('playlist ricevuta')
            raw = iter(data.decode('utf-8').split('\n'))
            fileNames = []
            timeStamps = self.timeStamps[radio]
            lastLength = None
            contentDict = self.contents[radio]
            while True:
                try:
                    line = next(raw)
                    if line.startswith('#'):
                        if line.startswith('#EXTINF:'):
                            lastLength = int(float(line[len('#EXTINF:'):].rstrip(',')) * 1000)
                    elif line:
                        fileName = line.strip()
                        fileNames.append(fileName)
                        index = int(FindIndexRegEx.findall(fileName)[-1])
                        if not index in contentDict:
                            contentDict[index] = BaseStreamUrl.format(radioName) + fileName
                            timeStamps.append((lastLength, index))
                except:
                    break
#            print(timeStamps)
#            for line in data.split(b'\n'):
#                line = line.decode('utf-8')
#                if line.startswith('#'):
#                    if line.startswith('#EXTINF:'):
#                        length = float(line[len('#EXTINF:'):].rstrip(','))
#                        print(length)
#            contents = [r.decode('utf-8') for r in data.split(b'\n') if r.strip() and not r.lstrip().startswith(b'#')]
            if self.liveBtn.isDown():
                reordered = fileNames[-3:] + fileNames[-6:-3]
                for fileName in reordered:
                    if not self.nextToPlay and self.player.currentState != self.player.ActiveState:
                        self.nextToPlay = BaseStreamUrl.format(radioName) + fileName
    #                remoteFileName = f.decode('utf-8')
                    filePath = self.cacheDirs[radio] + fileName
                    if not QtCore.QFile.exists(filePath):
                        urlPath = BaseStreamUrl.format(radioName) + fileName
                        if not urlPath in self.queue:
                            self.queue.append(urlPath)
                            req = QtNetwork.QNetworkRequest(QtCore.QUrl(urlPath))
                            self.manager.get(req)
                if self.player.currentState != self.player.ActiveState:
                    QtCore.QTimer.singleShot(1000, self.loadPlaylist)
            elif (self.playToggleBtn.isChecked() and self.player.currentState != self.player.ActiveState and 
                not self.nextToPlay and self.seekSlider.value() < 2160):
                    now = QtCore.QTime.currentTime()
                    timeIter = iter(reversed(self.timeStamps[radio]))
                    seekPos = 2160
                    sliderPos = self.seekSlider.value()
                    while seekPos > sliderPos:
                        length, index = next(timeIter)
                        now = now.addMSecs(-length)
                        seekPos -= 1
                    self.goToIndex(index)
#                    if index in self.cache[radio]:
#                        self.goToIndex(index)
#                    else:
#                        urlPath = self.contents[radio][index]
#                        self.nextToPlay = urlPath
#                        if not urlPath in self.queue:
#                            self.queue.append(urlPath)
#                            req = QtNetwork.QNetworkRequest(QtCore.QUrl(urlPath))
#                            self.manager.get(req)
#            contentDict = {}
#            for fileName in contents:
#                index = int(FindIndexRegEx.findall(fileName)[-1])
#                contentDict[index] = BaseStreamUrl.format(radioName) + fileName
#            self.contents[radio].update(contentDict)
            toRemove = []
            for index in self.requestIndexQueue:
                if not index in self.contents[radio]:
                    print('index {} non esiste ancora'.format(index), index)
                    if not self.playlistRequestTimer.isActive():
                        self.loadPlaylist()
                    continue
                toRemove.append(index)
                urlPath = self.contents[radio][index]
                if not urlPath in self.queue:
                    self.queue.append(urlPath)
                    req = QtNetwork.QNetworkRequest(QtCore.QUrl(urlPath))
                    self.manager.get(req)
            while toRemove:
                self.requestIndexQueue.remove(toRemove.pop())
        elif url.startswith(SongLogBaseUrl):
#            data = bytes((reply.readAll()))
            print('song log received!', radio)
            try:
                currentLog = self.songLogs[SongLogUrls.index(url)]
                songList = json.loads(data.decode('utf-8'))
                if not currentLog:
                    currentLog.extend(songList)
                else:
                    for song in songList:
                        if song not in currentLog:
                            currentLog.insert(0, song)
                self.reloadLog()
            except Exception as e:
                print('Song log not parsed!', e)
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
            indexStr = FindIndexRegEx.findall(fileName)[-1]
            index = int(indexStr)
#            if self.player.currentState != self.player.ActiveState and self.playToggleBtn.isChecked():
            if url == self.nextToPlay:
                self.nextToPlay = None
                pre = fileName.index(indexStr)
                self.player.setFileNameTemplate(fileName[:pre], fileName[pre + len(indexStr):])
                self.player.start(index)
                self.timeStampTimer.start()
                self.updateTimeStamp()
                self.playToggleBtn.blockSignals(True)
                self.playToggleBtn.setChecked(True)
                self.playToggleBtn.blockSignals(False)
            self.cache[radio][index] = fileName
            self.seekSlider.update()
#        print('reply!', url.endswith(PlaylistFileName))

    def reloadLog(self):
        html = '<xhtml><body>'
        for song in self.songLogs[self.lastRadio]:
            artist = song.get('artist')
            if isinstance(artist, dict):
                artist = artist.get('name')
            if not artist:
                print('no artist?', song.get('artist'))
                artist = '(no artist)'
            title = song.get('title', '(no title)')
            displayTime = song.get('displayTimeOfPlayback')
            realTime = song.get('timeOfPlayback')
            html += '''
                <a href="radio/{radio}/{realTime}">
                {displayTime}: {title} - {artist}
                </a><br/>
            '''.format(
                radio=self.lastRadio, 
                realTime = realTime, 
                displayTime = displayTime, 
                title = title, 
                artist = artist, 
                )
        html += '</body></xhtml>'
        self.nowPlaying.setHtml(html)

    def goToTime(self):
        self.timeEdit.lineEdit().deselect()
        self.playToggleBtn.setFocus()
        time = self.timeEdit.time()
        now = QtCore.QTime.currentTime()
        if time.secsTo(now) > 216000:
            print('too old!')
            return
        if not self.timeStamps[self.lastRadio]:
            print('playlist empty, reload')
            self.loadPlaylist(self.lastRadio)
            QtCore.QTimer.singleShot(100, self.goToTime)
            return
        print('now', now)
        timeIter = iter(reversed(self.timeStamps[self.lastRadio]))
        sliderPos = 2160
        while now > time:
            length, index = next(timeIter)
            now = now.addMSecs(-length)
            sliderPos -= 1
        print(now)
        self.setRadio(self.lastRadio)
        self.goToIndex(index)
        self.seekSlider.setValue(sliderPos)

    def goToClickedTime(self, url):
        contents = url.toString().split('/')
        radio = int(contents[-2])
        time = QtCore.QTime.fromString(contents[-1])
        now = QtCore.QTime.currentTime()
        if time.secsTo(now) > 216000:
            print('too old!')
            return
        if not self.timeStamps[radio]:
            print('playlist empty, reload')
            self.loadPlaylist(radio)
            QtCore.QTimer.singleShot(100, lambda: self.goToClickedTime(url))
            return
        print('now', now)
        timeIter = iter(reversed(self.timeStamps[radio]))
        sliderPos = 2160
        while now > time:
            length, index = next(timeIter)
            now = now.addMSecs(-length)
            sliderPos -= 1
        print(now)
        self.setRadio(radio)
        self.goToIndex(index)
        self.seekSlider.setValue(sliderPos)

    def goToIndex(self, index):
        print('go to index', index)
        fileName = self.cache[self.lastRadio].get(index)
        if fileName:
            print('exists')
            self.nextToPlay = None
            self.player.stop()
            indexStr = str(index)
            pre = fileName.index(indexStr)
            self.player.setFileNameTemplate(fileName[:pre], fileName[pre + len(indexStr):])
            self.player.start(index)
            self.timeStampTimer.start()
            self.updateTimeStamp()
            self.playToggleBtn.blockSignals(True)
            self.playToggleBtn.setChecked(True)
            self.playToggleBtn.blockSignals(False)

        else:
            print('not yet')
            urlPath = self.contents[self.lastRadio][index]
            if not urlPath in self.queue:
                self.queue.append(urlPath)
                req = QtNetwork.QNetworkRequest(QtCore.QUrl(urlPath))
                self.manager.get(req)
            self.nextToPlay = urlPath
#            QtCore.QTimer.singleShot(100, lambda: self.goToIndex(index))
#            filePath = self.cacheDirs[self.lastRadio] + fileName
#            if not QtCore.QFile.exists(filePath):
#                urlPath = BaseStreamUrl.format(RadioNames[self.lastRadio]) + fileName
#                if not urlPath in self.queue:
#                    self.queue.append(urlPath)
#                    req = QtNetwork.QNetworkRequest(QtCore.QUrl(urlPath))
#                    self.manager.get(req)
#                QtCore.QTimer.singleShot(100, lambda: self.goToIndex(index))


    def timeReference(self):
        return QtCore.QTime.currentTime().addSecs(-10)

    def stepVolume(self, amount):
        self.setVolume(self.volume() + amount)

    def volumeUp(self):
        self.stepVolume(VolumeStep)

    def volumeDown(self):
        self.stepVolume(-VolumeStep)

    def seekAmount(self, amount):
        amount *= self.settings.value('seekAmount', 2, type=int)
        self.seekSlider.setValue(self.seekSlider.value() + amount)
        self.seek()

    def quit(self):
        if self.settings.value('askToQuit', True, type=bool):
            if QtWidgets.QMessageBox.question(self, 'Quit?', 
                'Do you want to quit?', QtWidgets.QMessageBox.Ok|QtWidgets.QMessageBox.Cancel) != QtWidgets.QMessageBox.Ok:
                    return
        if self.close():
            print('quitto', self.player.currentState)
#            if not self.settings.value('useDefaultRadio')
            if self.settings.value('playOnStart', -2, type=int) < 0:
                if self.player.currentState == self.player.ActiveState:
                    print('play')
                    self.settings.setValue('playOnStart', -2)
                else:
                    print('stop')
                    self.settings.setValue('playOnStart', -1)
            self.player.stop()
            self.settings.sync()
            QtWidgets.QApplication.quit()

    def eventFilter(self, source, event):
        if source == self.playToggleBtn:
            # maybe set NoFocus to everything?
            if event.type() == QtCore.QEvent.KeyPress:
                if event.key() in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Plus):
                    self.volumeUp()
                    return True
                elif event.key() in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Minus):
                    self.volumeDown()
                    return True
                elif event.key() == QtCore.Qt.Key_Left:
                    self.seekAmount(-1)
                    return True
                elif event.key() == QtCore.Qt.Key_Right:
                    self.seekAmount()
                    return True
                elif not event.key() in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
                    return False
        elif source == self.timeEdit:
            if event.type() == QtCore.QEvent.FocusIn:
                self.updateTimeLimits()
            elif event.type() == QtCore.QEvent.KeyPress and event.key() in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
                res = super().eventFilter(source, event)
                self.goToTime()
                return res
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
            if self.settings.value('storeGeometry', True, type=bool):
                self.restoreGeometry(self.settings.value('geometry', type=QtCore.QByteArray))
#            self.setFixedHeight(self.sizeHint().height())
#            if self.settings.value('playOnStart', True, type=bool):
#                QtCore.QTimer.singleShot(0, lambda: self.playToggleBtn.setChecked(True))
#            if self.recordTree.parent() != self.centralWidget():
#                self.setFixedHeight(self.sizeHint().height())
#            self.recordTree.resizeColumnToContentsm

    def closeEvent(self, event):
        if self.settings.value('storeGeometry', True, type=bool):
            self.settings.setValue('geometry', self.saveGeometry())
#        self.settings.setValue('recordDockGeo', self.recordDock.saveGeometry())
        if not self.settings.contains('trayIcon'):
            msgBox = QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Question, 
                'Close RSI Play?', 
                'Do you want to keep RSIPlay running?', 
                parent=self
                )
            hideToTrayBtn = msgBox.addButton(
                'Hide to tray', msgBox.AcceptRole)
            msgBox.addButton(
                'Quit', msgBox.AcceptRole)
#            quitOnCloseBtn.setIcon(QtGui.QIcon.fromTheme('application-exit'))
            cancelBtn = msgBox.addButton(
                'Cancel', msgBox.RejectRole)
            msgBox.exec_() 
            if msgBox.clickedButton() == cancelBtn:
                event.ignore()
                return
            else:
                self.settings.setValue('closeToTray', msgBox.clickedButton() == hideToTrayBtn)
            self.settings.setValue('trayIcon', True)
        if self.useTrayIcon() and self.settings.value('closeToTray', False, type=bool):
                QtWidgets.QApplication.setQuitOnLastWindowClosed(False)

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
    if playerWindow.useTrayIcon() and not playerWindow.settings.value('startToTray', False, type=bool):
        playerWindow.show()
    sys.exit(app.exec_())
