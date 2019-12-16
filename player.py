#!/usr/bin/env python3

import re
from math import sqrt
import pyaudio
import numpy as np
import pydub
from PyQt5 import QtCore, QtGui, QtWidgets, QtNetwork, uic

findIndex = re.compile('\d+')
baseUrl = 'https://lsaplus.swisstxt.ch/audio/{}_96.stream/'
playlistFile = 'chunklist_DVR.m3u8'

shortNames = 'uno', 'due', 'tre'
radioNames = tuple('rete{}'.format(n) for n in shortNames)
radioTitles = tuple('Rete{}'.format(n.title()) for n in shortNames)


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
        self.curve = QtCore.QEasingCurve(QtCore.QEasingCurve.InCubic)

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
        overlap = 2048
        nextData = self.getData(self.currentIndex + 1)
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
        self.slider.setMaximum(100)
        self.slider.setValue(100)
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
        print('wheehe')
        step = self.slider.pageStep()
        if event.angleDelta().y() < 0 or event.angleDelta().x() < 0:
            step *= -1
        self.setVolume(self.volume() + step)

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
        centerY = self.rect().center().y()
        rect = QtCore.QRectF(0, 0, baseSize, baseSize)
        rect.moveCenter(QtCore.QPointF(self.baseWidth / 2, centerY - 1))
        qp.drawRoundedRect(rect, 2, 2)

        iconSize = self.iconSize
        pos = (self.height() - iconSize) / 2 - 1
        qp.drawPixmap(pos, pos, self.currentIcon.pixmap(iconSize))

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
    hourBackground = QtGui.QColor(255, 255, 255, 128)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
#        self.setMouseTracking(True)

        fm = self.fontMetrics()
        charWidths = max([fm.width(str(n)) for n in range(10)])
        self.hourWidth = charWidths * 2 + 2
        self.hourMinuteWidth = self.hourWidth * 2 + fm.width(':')

        self.topMargin = fm.height()

        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
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
            if self.quarterSize >= 32:
                qp.setPen(self.quarterPen)
                y = self.topMargin * .85
                for tick in self.quarterTicks:
                    qp.drawLine(tick, y, tick, self.topMargin)
            qp.restore()

        hourRect = QtCore.QRect(2, 0, self.hourSize - 2, self.topMargin)
        hour = self.leftHour
        fm = self.slider.fontMetrics()
        for tick in self.hourTicks:
            qp.drawLine(tick, 0, tick, self.topMargin)
            timeStr = '{:02}:00'.format(hour)
            textRect = fm.boundingRect(hourRect.translated(tick, 0), 
                QtCore.Qt.AlignLeft|QtCore.Qt.AlignTop, timeStr).adjusted(0, 0, 2, 0)
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


class RsiPlayer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi('player.ui', self)

        self.settings = QtCore.QSettings()
        defaultRadio = self.settings.value('defaultRadio', 0, type=int)
        lastRadio = self.settings.value('lastRadio', defaultRadio, type=int)
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

        self.rete1Btn.buttonPixmap = QtGui.QPixmap('reteuno.png')
        self.rete2Btn.buttonPixmap = QtGui.QPixmap('retedue.png')
        self.rete3Btn.buttonPixmap = QtGui.QPixmap('retetre.png')

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

        self.player = Player(self)
        self.player.request.connect(self.requestIndex)

        self.volumeSlider.volumeChanged.connect(self.setVolume)
        self.volumeSlider.setVolume(self.settings.value('volume', 100, type=int))

        self.lastRadio = -1
        self.setRadio(lastRadio)

        self.referenceTimer = QtCore.QTimer(interval=10000, timeout=self.seekSlider.updateLabelPositions)
        self.referenceTimer.start()
        self.playlistRequestTimer = QtCore.QTimer(singleShot=True, interval=9000, timeout=self.loadPlaylist)
        self.timeStampTimer = QtCore.QTimer(interval=1000, timeout=self.updateTimeStamp)

        self.recordModel = QtGui.QStandardItemModel()
        self.recordTree.setModel(self.recordModel)
        self.loadRecordings()

    def loadRecordings(self):
        from random import randrange
        locale = QtCore.QLocale()
        self.recordModel.clear()
        self.recordModel.setHorizontalHeaderLabels(['Network', 'Start', 'End', 'Duration'])
        for radio, title in enumerate(radioTitles):
            radioItem = QtGui.QStandardItem(title)
            self.recordModel.appendRow(radioItem)
            items = randrange(1, 5)
            for i in range(items):
                titleItem = QtGui.QStandardItem('Recording {}'.format(i + 1))
                start = QtCore.QDateTime.currentDateTime()
                start = start.addDays(randrange(1, 10))
                start = start.addSecs(randrange(86400))
                startItem = QtGui.QStandardItem(locale.toString(start, QtCore.QLocale.ShortFormat))
                duration = randrange(120, 7200)
                endItem = QtGui.QStandardItem(locale.toString(start.addSecs(duration), QtCore.QLocale.ShortFormat))
                m, s = divmod(duration, 60)
                h, m = divmod(m, 60)
                durationItem = QtGui.QStandardItem(QtCore.QTime(h, m, s).toString('HH:mm:ss'))
                subItems = [titleItem, startItem, endItem, durationItem]
                for item in subItems[1:]:
                    item.setFlags(item.flags() & ~ QtCore.Qt.ItemIsEditable)
                radioItem.appendRow(subItems)
        self.recordTree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.recordTree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.recordTree.header().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        self.recordTree.header().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.recordTree.expandAll()

    def updateTimeStamp(self):
        if self.timeEdit.hasFocus():
            return
        if self.liveBtn.isDown():
            self.timeEdit.setTime(self.timeReference())

    def setVolume(self, volume):
        self.player.setVolume(volume)
        self.settings.setValue('volume', volume)

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
        self.setWindowTitle('RSI - {}'.format(radioTitles[self.radioGroup.checkedId()]))
#        if not self.playToggleBtn.isChecked():
#            self.lastRadio = self.radioGroup.checkedId()
#            return
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

        if self.lastRadio < 0 or self.lastRadio == radio:
            self.lastRadio = radio
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
#            radio = 
#            cacheDict = self.playCache
#            self.playCache
#        print('reply!', url.endswith(playlistFile))

    def timeReference(self):
        return QtCore.QTime.currentTime().addSecs(-10)

#    def togglePlay(self, state):
#        self.playToggleBtn.setIcon(self.playIcons[state])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.seekSlider.updateLabelPositions()
        self.referenceTimer.start()


if __name__ == '__main__':
    import sys
    app = QtWidgets.QApplication(sys.argv)
    app.setOrganizationName('jidesk')
    app.setApplicationName('PlayRSI')
#    app.setStyle(QtWidgets.QStyleFactory.create('breeze'))
#    app.setStyle(QtWidgets.QStyleFactory.create('windows'))
    playerWindow = RsiPlayer()
    playerWindow.show()
    sys.exit(app.exec_())
