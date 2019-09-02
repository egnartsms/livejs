;; -*- lexical-binding: t; -*-
(require 'live/server "live-server")


(defconst lv-code-browser-bufname
  "*LiveJS Code Browser*")


(defconst lv-js:dumpRootContents
  "
for (let [key, value] of Object.entries(this)) {
  if (this.nontrackedKeys.includes(key)) {
    continue;
  }

  this.sendResponse([key, this.serialize(value, 0)]);
}
")


(defvar live-mode-syntax-table
  (make-syntax-table js-mode-syntax-table))


(define-derived-mode live-mode special-mode "LiveJS"
  "Major mode for interacting with LiveJS system"
  :abbrev-table nil
  :syntax-table live-mode-syntax-table
  )


(defun lv-populate-browser ()
  (interactive)
  (let ((inhibit-read-only t))
    (delete-region (point-min) (point-max)))
  (let ((lvbuf (current-buffer)))
    (lv-set-callback
     (lambda (entry)
       (with-current-buffer lvbuf
	 (let ((inhibit-read-only t)
	       (key (aref entry 0))
	       (val (aref entry 1)))
	   (insert key "\n" val "\n\n")))))
    (lv-send lv-js:dumpRootContents)))


(defun lv-browse ()
  (interactive)
  (let ((buf (get-buffer lv-code-browser-bufname)))
    (unless buf
      (with-current-buffer
	  (setf buf (get-buffer-create lv-code-browser-bufname))
	(live-mode)
	(lv-populate-browser)))
    (display-buffer buf)))
	
    

(provide 'live/mode)
