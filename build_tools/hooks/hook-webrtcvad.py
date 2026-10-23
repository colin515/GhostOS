"""The import is webrtcvad, but this project installs the maintained wheels distribution."""
from PyInstaller.utils.hooks import copy_metadata

# Override the contrib hook, which requests metadata from the older webrtcvad distribution.
datas = copy_metadata('webrtcvad-wheels')
hiddenimports = ['_webrtcvad']
