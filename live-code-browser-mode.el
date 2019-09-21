;; -*- lexical-binding: t; -*-
(require 'live-server)
(require 'live-util)


(defconst lv-code-browser-bufname
  "*LiveJS Code Browser*")


(defconst lv-js:get
  "
for (let [key, value] of Object.entries(this)) {
  if (this.nontrackedKeys.includes(key)) {
    continue;
  }

  this.sendResponse([key, this.serialize(value, 0)]);
}
")


(defvar lv-code-browser-syntax-table
  (make-syntax-table js-mode-syntax-table))


(defconst lv-code-browser-font-lock-defaults
  '(js--font-lock-keywords-2 nil nil nil))


(defvar lv-code-browser-edit-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "<C-return>") 'lv-code-browser-toggle-edit)
    map)
  "The map which is temporarily made active when editing module entries")


(defvar lv-code-browser-mode-map
  (let ((map (make-sparse-keymap)))
    (set-keymap-parent map special-mode-map)
    (define-key map (kbd "e") 'lv-code-browser-toggle-edit)
    map))


(defvar-local lv-code-browser-editing nil
  "Non-nil when editing a definition (entry)")


(defun lv-code-browser-toggle-edit ()
  (interactive)
  (if (not lv-code-browser-editing)
      (progn
	(let ((beg (field-beginning))
	      (end (field-end)))
	  (let ((inhibit-read-only t))
	    (put-text-property beg end 'inhibit-read-only t)))
	(use-local-map lv-code-browser-edit-map)
	(setf lv-code-browser-editing t)
	)
    (let ((beg (field-beginning))
	  (end (field-end)))
      (let ((inhibit-read-only t))
	(put-text-property beg end 'inhibit-read-only nil)))
    (use-local-map lv-code-browser-mode-map)
    (setf lv-code-browser-editing nil)))


(define-derived-mode lv-code-browser-mode special-mode "LiveJS"
  "Major mode for interacting with LiveJS system"
  :abbrev-table nil
  :syntax-table lv-code-browser-syntax-table

  (setq font-lock-defaults lv-code-browser-font-lock-defaults)
  (setq-local font-lock-support-mode nil)
  )


(defun lv-populate-browser ()
  (interactive)
  (let ((lvbuf (current-buffer)))
    (lv-set-callback
     (lambda (entries)
       (with-current-buffer lvbuf
	 (let ((inhibit-read-only t))
	   (delete-region (point-min) (point-max))
	   (mapc
	    (lambda (entry)
	      (goto-char (point-max))
	      (let ((key (aref entry 0))
		    (val (aref entry 1)))
		(let ((beg (point)))
		  (insert key "\n")
		  (put-text-property beg (point) 'Field 'key))
		(let ((beg (point)))
		  (insert val "\n")
		  (put-text-property beg (point) 'Field 'value)
		  (font-lock-fontify-region beg (point)))))
	    entries))))))
  (lv-send "this.sendAllEntries()"))


(defun lv-browse ()
  (interactive)
  (pop-to-buffer
   (lv-get-buffer-init
    lv-code-browser-bufname
    (lambda ()
      (buffer-disable-undo)
      (lv-code-browser-mode)
      (lv-populate-browser)))
   ))


(defun lv-js-temp-buf ()
  
  ) 


(provide 'live-mode)
