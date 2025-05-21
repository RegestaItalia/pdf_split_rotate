import win32serviceutil
import win32service
import win32event
import servicemanager
import subprocess
import sys
import os

class PDFSplitRotateService(win32serviceutil.ServiceFramework):
    _svc_name_ = "PDFSplitRotateService"
    _svc_display_name_ = "PDF Split Rotate Watcher"
    _svc_description_ = "Watches a folder and runs pdf_split_rotate.py automatically."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.process = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.process:
            self.process.terminate()
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ""))
        self.main()

    def main(self):
        script_path = os.path.join(os.path.dirname(__file__), "pdf_split_rotate.py")
        python_exe = sys.executable
        while True:
            self.process = subprocess.Popen([python_exe, script_path])
            rc = win32event.WaitForSingleObject(self.hWaitStop, 1000)
            if rc == win32event.WAIT_OBJECT_0:
                break
            # Check if process has exited, restart if needed
            if self.process.poll() is not None:
                self.process = None
                continue

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(PDFSplitRotateService)
