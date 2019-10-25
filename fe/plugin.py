import os
import sys

livejs_package = os.path.realpath(os.path.join(__file__, '..'))
if livejs_package not in sys.path:
    sys.path.append(livejs_package)

from live.sublime import *  # noqa
