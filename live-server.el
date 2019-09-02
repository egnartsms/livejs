;; -*- lexical-binding: t; -*-
(require 'json)
(require 'live/writer "live-writer")


(defconst lv-server-port 8000)

(defvar lv-server nil)

(defvar lv-websocket nil
  "Websocket used to communicate with JS"
  )

(defvar lv-handlers
  (list
   (cons
    '(:GET . "^/wsconnect$")
    (lambda (request)
      (if (ws-websocket-connect request 'lv-web-socket-handler)
	  (prog1
	      :keep-alive
	    (setf lv-websocket request)
	    (lv-initialize))
	nil)))
   (cons
    (lambda (request)
      (let* ((fname (cdr (assoc :GET (ws-request-headers request))))
	     (fullname (concat "/home/serhii/hack/livejs" fname)))
	(and (not (string= fname "/"))
	     (file-exists-p fullname))))
    (lambda (request)
      (let* ((fname (cdr (assoc :GET (ws-request-headers request))))
	     (fullname (concat "/home/serhii/hack/livejs" fname)))
	(ws-send-file (ws-request-process request) fullname))))
   (cons
    '(:GET . "^/$")
    (lambda (request)
      (ws-send-file (ws-request-process request)
		    "/home/serhii/hack/livejs/page.html")))
   (cons
    (lambda (_request) t)
    (lambda (request)
      (ws-send-404 (ws-request-process request))))))


(defvar lv-pending-callback nil
  "The function to be invoked with the next message from JS")


(defun lv-set-callback (&optional cb)
  (setf lv-pending-callback cb))


(defun lv-master-handler (request)
  "This is just another indirection layer to easily change lv-handlers' value"
  (ws-call-handler request lv-handlers))


(defun lv-initialize ()
  "Initialize the JS world"
  (ws-websocket-send
   lv-websocket
   (format "this.jsIndent = %s; this.jsIndentStr = ' '.repeat(this.jsIndent);"
	   lv-root-obj-indent)))


(defun lv-web-socket-handler (payload)
  (let* ((json (let ((json-key-type 'keyword))
		 (json-read-from-string payload)))
	 (type (alist-get :type json)))
    ;; (message "got %s" json)
    (pcase-exhaustive type
      ("msg"
       (message (alist-get :msg json)))
      ("response"
       (let ((response (alist-get :response json)))
    	 (if lv-pending-callback
    	     (funcall lv-pending-callback response)
    	   (error "From JS arrived response that Lisp was not waiting: %s"
    		  response))))
      ("save-key"
       (let ((key (alist-get :key json))
    	     (value (alist-get :value json)))
    	 (lv-save-key key value)
    	 )))
    ))



;; High-level interface
(defun lv-send (msg)
  (interactive "MJS to eval: ")
  (ws-websocket-send lv-websocket msg))


(defun lv-start ()
  (interactive)
  (if lv-server
      (message "The server is already started")
    (setf lv-server
	  (ws-start lv-handlers lv-server-port "*web-server-log*"))))


(defun lv-stop ()
  (interactive)
  (if lv-server
      (progn
	(ws-stop lv-server)
	(setf lv-server nil))
    (message "The server is not started")))


;; (lv-start)

;; (lv-send "
;; this.Point = function (x, y) {
;;    this.x = x;
;;    this.y = y;
;; };

;; this.O = new this.Point(.0, .0);
;; this.R = new this.Point(10., 0.);

;; this.arr = [this.O, this.R, this.Point, 10, '10'];
;; ")


;; (lv-send "
;;   this.saveKey('Point');
;; ")



;; (lv-send "
;;   this.getValue(this.saveKey, 0);
;; ")

(provide 'live/server)
