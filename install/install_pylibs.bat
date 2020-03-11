set PATH=c:\python35\;c:\python35\scripts\;%PATH%
python get-pip.py
python -m pip install --upgrade pip wheel setuptools
python -m pip install -r requirements.txt