;; -*- lexical-binding: t; -*-
(defconst lv-root-obj-indent 3
  "Indentation in the root object serialized JS file"
  )

(defconst lv-root-js-file-name
  (concat default-directory "root.js"))

(defconst lv-root-js-buffer-name
  " root.js")




;; Primitives for serializing the code in source files
(defun lv-root-js-buffer ()
  (or (get-buffer lv-root-js-buffer-name)
      (with-current-buffer (get-buffer-create lv-root-js-buffer-name)
	(insert-file-contents lv-root-js-file-name t)
	(current-buffer))))


(defconst lv-re-final-brace
  (rx-to-string
   `(: bol "};")))


(defconst lv-re-entry-start
  (rx-to-string
   `(: bol (or (: (= ,lv-root-obj-indent space) (group (* alphanumeric)) ": ")
	       "};"))))


(defun lv-re-entry-start-of (key)
  (if key
      (rx-to-string
       `(: bol (= ,lv-root-obj-indent space) (group ,key) ": "))
    lv-re-entry-start))


;; (defconst lv-re-entry-end
;;   (rx-to-string
;;    `(: bol (= ,lv-root-obj-indent space) "}" (? ",") (* space) "\n")))


(defun lv-fwd-search-entry (&optional key)
  "Go to KEY, set point at . Return t if found and moved, nil if not"
  (let ((found (re-search-forward (lv-re-entry-start-of key) nil t)))
    (when found
      (forward-line 0)
      t)))


(defun lv-next-entry ()
  (forward-line)
  (lv-fwd-search-entry))


(defun lv-goto-end ()
  (goto-char (point-min))
  (re-search-forward lv-re-final-brace nil nil)
  (forward-line 0))


;; (defun lv-fwd-search-entry-end ()
;;   "Fwd search for nearest entry end.  Leave point right after the entry"
;;   (re-search-forward lv-re-entry-end))


;; (defun lv-bwd-search-entry-end ()
;;   "Bwd search for nearest entry end.  Leave point right after the entry"
;;   (re-search-backward lv-re-entry-end)
;;   (goto-char (match-end 0)))


(defun lv-erase-entry ()
  "Erase the entry we're looking at (the point is at bol).

Also delete all the whitespace after the entry
"
  (sm-check (bolp))
  (delete-region (point)
		 (sm-point-would-be (lv-next-entry))))


(defun lv-insert-entry (key value)
  "Insert key: value "
  (insert-char ?\s lv-root-obj-indent)
  (insert key ": " value ",\n\n"))


(defun lv-save-key (key value)
  "Save VALUE under KEY"
  (with-current-buffer (lv-root-js-buffer)
    (goto-char (point-min))
    (if (lv-fwd-search-entry key)
	(progn
	  (lv-erase-entry)
	  (lv-insert-entry key value))
      (lv-goto-end)
      ;; to make sure there's nothing after last entry and final "};"
      (lv-insert-entry key value))
    (save-buffer)))


(provide 'live/writer)
