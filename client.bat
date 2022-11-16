@ECHO off

IF NOT EXIST "venv\" (

	SET /P gumpf=You need to set up a venv! Check the running from source help for more info!
	EXIT /B 1
	
)

CALL venv\Scripts\activate.bat

REM You can copy this file to 'client-user.bat' and add in your own launch parameters here if you like, and a git pull won't overwrite the file.
REM Just tack new params on like this:
REM start "" "pythonw" client.pyw -d="E:\hydrus"

start "" "pythonw" client.pyw

REM Here is an alternate line that will keep the console open and see live log updates. Useful for boot/live debugging.
REM python client.py