from Components.MenuList import MenuList
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
from Tools.LoadPixmap import LoadPixmap
from enigma import eListboxPythonMultiContent, gFont, RT_HALIGN_LEFT, RT_VALIGN_CENTER
from skin import getSkinFactor, fonts, parameters


def applySkinFactor(*d):
	"""
	Multiply the numeric input by the skin factor
	and return the result as an integer.
	"""
	if len(d) == 1:
		return int(d[0] * getSkinFactor())
	return tuple([int(value * getSkinFactor()) if isinstance(value, (int, float)) else value for value in d])


def SelectionEntryComponent(description, value, index, selected, selectionListDescr=parameters.get("SelectionListDescr", applySkinFactor(25, 0, 650, 30))):
	dx, dy, dw, dh = selectionListDescr
	res = [
		(description, value, index, selected),
		(eListboxPythonMultiContent.TYPE_TEXT, dx, dy, dw, dh, 0, RT_HALIGN_LEFT | RT_VALIGN_CENTER, description)
	]
	if selected:
		selectionpng = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "icons/lock_on.png"))
	else:
		selectionpng = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "icons/lock_off.png"))
	ix, iy, iw, ih = parameters.get("SelectionListLock", applySkinFactor(0, 2, 25, 24))
	res.append((eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND, ix, iy, iw, ih, selectionpng))
	return res


class SelectionList(MenuList):
	def __init__(self, list=None, enableWrapAround=False):
		MenuList.__init__(self, list or [], enableWrapAround, content=eListboxPythonMultiContent)
		font = fonts.get("SelectionList", applySkinFactor("Regular", 20, 30))
		self.l.setFont(0, gFont(font[0], font[1]))
		self.l.setItemHeight(font[2])
		self.selectionListDescr = parameters.get("SelectionListDescr", applySkinFactor(25, 0, 650, 30))

	def addSelection(self, description, value, index, selected=True):
		self.list.append(SelectionEntryComponent(description, value, index, selected, self.selectionListDescr))
		self.setList(self.list)

	def toggleSelection(self):
		if len(self.list):
			idx = self.getSelectedIndex()
			item = self.list[idx][0]
			self.list[idx] = SelectionEntryComponent(item[0], item[1], item[2], not item[3], self.selectionListDescr)
			self.setList(self.list)

	def getSelectionsList(self):
		return [(item[0][0], item[0][1], item[0][2]) for item in self.list if item[0][3]]

	def toggleAllSelection(self):
		for idx, item in enumerate(self.list):
			item = self.list[idx][0]
			self.list[idx] = SelectionEntryComponent(item[0], item[1], item[2], not item[3], self.selectionListDescr)
		self.setList(self.list)

	def removeSelection(self, item):
		for it in self.list:
			if it[0][0:3] == item[0:3]:
				self.list.pop(self.list.index(it))
				self.setList(self.list)
				return

	def toggleItemSelection(self, item):
		for idx, i in enumerate(self.list):
			if i[0][0:3] == item[0:3]:
				item = self.list[idx][0]
				self.list[idx] = SelectionEntryComponent(item[0], item[1], item[2], not item[3], self.selectionListDescr)
				self.setList(self.list)
				return

	def sort(self, sortType=False, flag=False):
		# sorting by sortType:
		# 0 - description
		# 1 - value
		# 2 - index
		# 3 - selected
		self.list.sort(key=lambda x: x[0][sortType], reverse=flag)
		self.setList(self.list)

	def applySkin(self, desktop, parent):

		def selectionListDescr(value):
			self.selectionListDescr = list(map(int, value.split(",")))

		for (attrib, value) in self.skinAttributes[:]:
			try:
				locals().get(attrib)(value)
			except:
				pass
			else:
				self.skinAttributes.remove((attrib, value))

		# recreate the list with the new parameters parsed from skin
		for x in range(len(self.list)):
			description, value, index, selected = self.list[x][0]
			self.list[x] = SelectionEntryComponent(description, value, index, selected, self.selectionListDescr)
		self.setList(self.list)
		return MenuList.applySkin(self, desktop, parent)
