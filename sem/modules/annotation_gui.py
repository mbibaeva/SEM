"""
file: annotation_gui.py

author: Yoann Dupont

MIT License

Copyright (c) 2018 Yoann Dupont

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import print_function

import codecs
import glob
import logging
import os
import re
import sys

try:
    import Tkinter as tkinter
except ImportError:
    import tkinter

try:
    import ttk
except ImportError:
    from tkinter import ttk

try:
    from tkFont import Font
except ImportError:
    from tkinter.font import Font
try:
    import tkFileDialog
    tkinter.filedialog = tkFileDialog
except ImportError:
    import tkinter.filedialog
try:
    import ScrolledText
    tkinter.scrolledtext = ScrolledText
except ImportError:
    import tkinter.scrolledtext
try:
    import tkMessageBox
    tkinter.messagebox = tkMessageBox
except ImportError:
    import tkinter.messagebox

import sem
from sem.constants import NUL
from sem.misc import documents_from_list
from sem.storage.document import Document, SEMCorpus
from sem.storage.annotation import Tag, Annotation
from sem.logger import extended_handler
import sem.importers
from sem.gui.misc import find_potential_separator, find_occurrences, random_color, Adder2
from sem.gui.components import SEMTkTrainInterface, SearchFrame
from sem.gui.components import SemTkMasterSelector, SemTkLangSelector # TODO: remove
from sem.storage.annotation import str2filter
import sem.modules.tagger

annotation_gui_logger = logging.getLogger("sem.annotation_gui")
annotation_gui_logger.addHandler(extended_handler)

def update_annotations(document, annotation_name, annotations):
    annots = Annotation(annotation_name)
    annots.annotations = annotations
    try:
        reference = document.annotation(annotation_name).reference
    except:
        reference = None
    document.add_annotation(annots)
    if reference:
        document.set_reference(annotation_name, reference.name)

def check_in_tagset(tag, tagset):
    ok = tag in tagset
    if not ok:
        for the_tag in tagset:
            ok = the_tag.startswith(tag)
            if ok:
                break
    return ok

class AnnotationTool(tkinter.Frame):
    def __init__(self, parent, log_level, documents=None, tagset=None, *args, **kwargs):
        tkinter.Frame.__init__(self, parent, *args, **kwargs)
        
        annotation_gui_logger.setLevel(log_level)
        
        self.bind_all("<Alt-F4>", self.exit)
        
        self.resource_dir = os.path.join(sem.SEM_RESOURCE_DIR)
        
        self.parent = parent
        
        self.user = None
        self.doc = None
        self.doc_is_modified = False
        self.annotation_name = None
        self.annotations = []
        self.annotations_tick = 0
        
        self.shortcuts = [
            ["Ctrl+o", ["open file", self.openfile_gui], [[self, True]]], # True = bind_all
            ["Ctrl+Shift+o", ["open url", self.openurl], [[self, True]]], # True = bind_all
            ["Ctrl+s", ["save", self.save], [[self, True]]], # True = bind_all
            ["Ctrl+t", ["train", self.train], [[self, True]]], # True = bind_all
            ["Ctrl+f", ["find", self.find_in_text], [[self, True]]], # True = bind_all
        ]
        
        
        self.lines_lengths = []
        
        #
        # menu
        #
        self.global_menu = tkinter.Menu(self.parent)
        # file menu
        self.file_menu = tkinter.Menu(self.global_menu, tearoff=False)
        self.global_menu.add_cascade(label="File", underline=0, menu=self.file_menu)
        self.file_menu.add_command(label="Open...", underline=0, command=self.openfile_gui, accelerator="Ctrl+O")
        self.file_menu.add_command(label="Open url...", underline=5, command=self.openurl, accelerator="Ctrl+Shift+O")
        self.file_menu.add_command(label="Save to...", underline=0, command=self.save, accelerator="Ctrl+S")
        self.saveas_menu = tkinter.Menu(self.file_menu, tearoff=False)
        self.file_menu.add_cascade(label="Save as...", underline=5, menu=self.saveas_menu)
        self.saveas_menu.add_command(label="BRAT corpus", underline=0, command=self.save_brat)
        self.saveas_menu.add_command(label="GATE corpus", underline=0, command=self.save_gate)
        self.saveas_menu.add_command(label="TEI ANALEC corpus", underline=4, command=self.save_tei_analec)
        self.saveas_menu.add_command(label="TEI REDEN corpus", underline=4, command=self.save_tei_reden)
        self.saveas_menu.add_command(label="JSON corpus", underline=0, command=self.save_json)
        self.file_menu.entryconfig("Save to...", state=tkinter.DISABLED)
        self.file_menu.entryconfig("Save as...", state=tkinter.DISABLED)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="load tagset...", underline=5, command=self.load_tagset_gui)
        self.file_menu.add_command(label="Load master...", underline=5, command=self.load_pipeline)
        # edit menu
        self.edit_menu = tkinter.Menu(self.global_menu, tearoff=False)
        self.global_menu.add_cascade(label="Edit", underline=0, menu=self.edit_menu)
        self.edit_menu.add_command(label="Preferences...", command=self.preferences)
        # ? menu
        self.qm_menu = tkinter.Menu(self.global_menu, tearoff=False)
        self.global_menu.add_cascade(label="?", menu=self.qm_menu)
        self.qm_menu.add_command(label="About SEM...", command=self.about_sem)
        # final
        self.parent.config(menu=self.global_menu)
        
        self.new_type = tkinter.StringVar()
        self.SPARE_COLORS_DEFAULT = []
        self.SPARE_COLORS_DEFAULT = [{"background":"#CCCCCC", "foreground":"#000000"}, {'foreground': '#374251', 'background': '#9ca9bc'}, {'foreground': '#4b3054', 'background': '#b28fbf'}, {'foreground': '#625e2d', 'background': '#d0cb99'}, {'foreground': '#454331', 'background': '#a7a383'}, {'foreground': '#79a602', 'background': '#e7fea8'}, {'background': '#C8A9DC', 'foreground': '#542D6E'}, {'background': '#C9B297', 'foreground': '#5C4830'}, {'foreground': '#426722', 'background': '#aad684'}, {'foreground': '#886c11', 'background': '#f1da91'}, {'foreground': '#275a5f', 'background': '#85c6cc'}, {'foreground': '#0a9b47', 'background': '#a3fac8'}, {'foreground': '#729413', 'background': '#e3f5af'}, {'foreground': '#a22800', 'background': '#ffb299'}, {'foreground': '#254084', 'background': '#bccaed'}, {'foreground': '#601194', 'background': '#d7a8f6'}, {'foreground': '#6c4c45', 'background': '#e6dad7'}, {'foreground': '#1461a1', 'background': '#cce5f9'}, {'foreground': '#8a570d', 'background': '#f4c888'}, {'foreground': '#813058', 'background': '#eecfde'}]
        self.SPARE_COLORS_DEFAULT.extend([{"background":"#DDFFDD", "foreground":"#008800"}, {"background":"#CCCCFF", "foreground":"#0000FF"}, {"background":"#CCEEEE", "foreground":"#008888"}, {"background":"#FFCCCC", "foreground":"#FF0000"}]) # at the end for "pop"
        self.spare_colors = self.SPARE_COLORS_DEFAULT[:]
        
        self.bind_all("<Control-o>", self.openfile_gui)
        self.bind_all("<Control-O>", self.openurl)
        self.bind_all("<Control-s>", self.save)
        self.bind_all("<Control-t>", self.train)
        self.bind_all("<Control-f>", self.find_in_text)
        self.focus_set()
        
        self.bind_all("<Tab>", self.tab)
        self.bind_all("<Shift-Tab>", self.shift_tab)
        
        self.available_chars_set = list(u"abcdefghijklmnopqrstuvwxyz") + [u'F1', u'F2', u'F3', u'F4', u'F5', u'F6', u'F7', u'F8', u'F9', u'F10', u'F11', u'F12']
        self.SELECT_TYPE = u"-- select type --"
        self.wish_to_add = []
        
        self.current_annotations = Annotation("CurrentAnnotations")
        self.adder = None

        self.toolbar = ttk.Frame(self)
        self.toolbar.pack(side="top", fill="x")

        self.train_btn = ttk.Button(self.toolbar, text="train", command=self.train)
        self.train_btn.pack(side="left")
        self.train_btn.configure(state=tkinter.DISABLED)

        self.tag_document_btn = ttk.Button(self.toolbar, text="tag document", command=self.tag_document)
        self.tag_document_btn.pack(side="left")
        self.tag_document_btn.configure(state=tkinter.DISABLED)

        #self.load_tagset_btn = ttk.Button(self.toolbar, text="load tagset", command=self.load_tagset_gui)
        #self.load_tagset_btn.pack(side="left")

        self.type_combos = []
        self.add_type_lbls = []
        self.annotation_row = ttk.PanedWindow(self, orient="horizontal")
        
        self.corpus_tree = ttk.Treeview(self.annotation_row)
        self.corpus_tree_scrollbar = ttk.Scrollbar(self.annotation_row, command=self.corpus_tree.yview)
        self.corpus_tree.configure(yscroll=self.corpus_tree_scrollbar.set)
        self.corpus_tree.heading("#0", text="corpus", anchor=tkinter.W)
        self.corpus_tree.bind("<<TreeviewSelect>>", self.load_document)
        self.corpus_documents = []
        self.corpus_id2doc = {}
        self.corpus_doc2id = {}
        
        self.text = tkinter.scrolledtext.ScrolledText(self.annotation_row, wrap=tkinter.WORD, font="Helvetica")
        self.text.configure(state="disabled")
        self.text.bind("<Shift-Tab>", self.shift_tab)
        self.search = SearchFrame(self.text)
        for char in self.available_chars_set:
            self.text.bind("<{0}>".format(char), self.handle_char)
            self.parent.bind("<{0}>".format(char), self.handle_char)
            if char.islower():
                self.text.bind("<{0}>".format(char.upper()), self.handle_char)
                self.parent.bind("<{0}>".format(char.upper()), self.handle_char)
        
        self.tree = ttk.Treeview(self.annotation_row)
        self.tree_scrollbar = ttk.Scrollbar(self.annotation_row, command=self.tree.yview)
        self.tree.configure(yscroll=self.tree_scrollbar.set)
        self.tree.heading("#0", text="annotation sets", anchor=tkinter.W)
        self.tree.bind("<<TreeviewSelect>>", self.select_from_tree)
        self.tree_ids = {}
        self.annot2treeitems = {}
        
        self.annotation_row.add(self.corpus_tree)
        self.annotation_row.add(self.corpus_tree_scrollbar)
        self.annotation_row.add(self.text)
        self.annotation_row.add(self.tree)
        self.annotation_row.add(self.tree_scrollbar)
        self.annotation_row.pack(side="left", fill="both", expand=True)
        
        self.text.bind("<Button-1>", self.click)
        self.text.bind("<Delete>", self.delete)
        self.parent.bind("<Delete>", self.delete)
        self.text.bind("<Shift-Delete>", self.delete_all)
        self.parent.bind("<Shift-Delete>", self.delete_all)
        self.text.bind("<Escape>", self.unselect)
        self.parent.bind("<Escape>", self.unselect)
        
        self.tree.bind("<Delete>", self.delete)
        self.tree.bind("<Shift-Delete>", self.delete_all)
        
        ## configuring a tag called BOLD
        bold_font = Font(self.text)
        bold_font.configure(weight="bold")
        self.text.tag_configure("BOLD", font=bold_font)
        
        self.workflow = None
        
        self.position2annots = {}
        self.tree_ids = {}
        self.annot2treeitems = {}
        self.ner2history = {}
        
        # preferences
        self._whole_word = tkinter.BooleanVar()
        self._whole_word.set(True)
        self.wikinews_format = tkinter.BooleanVar()
        self.wikinews_format.set(False)
        
        self.pipeline = None
        
        if tagset:
            self.load_tagset(tagset)
        if documents:
            doc_list = []
            for doc in documents:
                doc_list.extend(glob.glob(doc))
            self.openfile(doc_list)
            ident = self.corpus_doc2id[self.corpus_documents[0].name]
            self.corpus_tree.selection_set(ident)
            self.corpus_tree.focus(ident)
            self.corpus_tree.see(ident)
            self.load_document()
        #skip_auth=> self.auth()
    
    @property
    def whole_word(self):
        return bool(self._whole_word.get())
    
    def exit(self, event=None):
        self.destroy()
        self.parent.destroy()
    
    def auth(self, event=None):
        authTop = tkinter.Toplevel()
        authTop.grab_set()
        auth_login = tkinter.StringVar(authTop, value="admin")
        auth_pw = tkinter.StringVar(authTop, value="")
        
        def close():
            sys.exit(0)
        
        authTop.protocol('WM_DELETE_WINDOW', close)
        
        def check_auth():
            import time, hashlib
            pwd = auth_pw.get()
            if pwd == "":
                print("Please enter non empty password")
            try:
                content = open(".users").read()
                if "d033e22ae348aeb5660fc2140aec35850c4da997aee5aca44055f2cd2f2ce4266909b69a5d96dad2\n" not in content:
                    print("Something fishy about your .user file, rewriting it with admin user only.")
                    with codecs.open(".users", "w") as O:
                        O.write("d033e22ae348aeb5660fc2140aec35850c4da997aee5aca44055f2cd2f2ce4266909b69a5d96dad2\n")
                    time.sleep(5.0)
                    sys.exit(1)
                h = hashlib.sha1()
                h.update(auth_login.get())
                login = h.hexdigest()
                h = hashlib.sha1()
                h.update(pwd)
                pw = h.hexdigest()
                checked = login + pw in content
                if checked:
                    self.user = auth_login.get()[:]
                    tkinter.messagebox.showinfo("Login success","Logged succesfuly as {0}".format(self.user))
                    
                    if self.user == "admin":
                        self.add_user_btn = ttk.Button(self.toolbar, text="add user", command=self.add_user)
                        self.add_user_btn.pack(side="left")
                    
                    authTop.destroy()
                else:
                    tkinter.messagebox.showerror("Login error", "Wrong login/password")
            except IOError:
                with codecs.open(".users", "w") as O:
                    O.write("d033e22ae348aeb5660fc2140aec35850c4da997aee5aca44055f2cd2f2ce4266909b69a5d96dad2\n")
                print("Could not find .user file, rewriting it with admin user only.")
        
        authLabel = tkinter.Label(authTop, text="Enter credentials:")
        authLabel.grid(row=0, column=0, sticky=tkinter.W+tkinter.E, columnspan=2)
        
        tkinter.Label(authTop, text='login').grid(row=1, column=0, sticky=tkinter.W)
        auth_login_entry = tkinter.Entry(authTop, textvariable=auth_login)
        auth_login_entry.grid(row=1, column=1, sticky=tkinter.W)
        tkinter.Label(authTop, text='password').grid(row=2, column=0, sticky=tkinter.W)
        auth_pw_entry = tkinter.Entry(authTop, textvariable=auth_pw, show="*")
        auth_pw_entry.grid(row=2, column=1, sticky=tkinter.W)
        
        login_btn = ttk.Button(authTop, text="login", command=check_auth)
        login_btn.grid(row=3, column=0, sticky=tkinter.W+tkinter.E, columnspan=2)
        
    def add_user(self, event=None):
        authTop = tkinter.Toplevel()
        authTop.grab_set()
        auth_login = tkinter.StringVar(authTop, value="admin")
        auth_pw = tkinter.StringVar(authTop, value="")
        
        def check_auth():
            import hashlib
            pwd = auth_pw.get()
            if pwd == "":
                print("Please enter non empty password")
                return
            try:
                lines = [line.strip() for line in open(".users").readlines()]
                if "d033e22ae348aeb5660fc2140aec35850c4da997aee5aca44055f2cd2f2ce4266909b69a5d96dad2" not in lines:
                    print("Something fishy about your .user file, rewriting it with admin user only.")
                    with codecs.open(".users", "w") as O:
                        O.write("d033e22ae348aeb5660fc2140aec35850c4da997aee5aca44055f2cd2f2ce4266909b69a5d96dad2\n")
                h = hashlib.sha1()
                h.update(auth_login.get())
                login = h.hexdigest()
                h = hashlib.sha1()
                h.update(auth_pw.get())
                pw = h.hexdigest()
                for line in lines:
                    if line.startswith(login):
                        tkinter.messagebox.showerror("Cannot add user", "User {0} already exists".format(auth_login.get()))
                        return
                
                with codecs.open(".users", "a") as O:
                    O.write("{0}{1}\n".format(login, pw))
                tkinter.messagebox.showinfo("New user","Succesfuly added user {0}".format(auth_login.get()))
                authTop.destroy()
            except IOError:
                with codecs.open(".users", "w") as O:
                    O.write("d033e22ae348aeb5660fc2140aec35850c4da997aee5aca44055f2cd2f2ce4266909b69a5d96dad2\n")
                print("Could not find .user file, rewriting it with admin user only.")
        
        authLabel = tkinter.Label(authTop, text="Enter credentials:")
        authLabel.grid(row=0, column=0, sticky=tkinter.W+tkinter.E, columnspan=2)
        
        tkinter.Label(authTop, text='login').grid(row=1, column=0, sticky=tkinter.W)
        auth_login_entry = tkinter.Entry(authTop, textvariable=auth_login)
        auth_login_entry.grid(row=1, column=1, sticky=tkinter.W)
        tkinter.Label(authTop, text='password').grid(row=2, column=0, sticky=tkinter.W)
        auth_pw_entry = tkinter.Entry(authTop, textvariable=auth_pw, show="*")
        auth_pw_entry.grid(row=2, column=1, sticky=tkinter.W)
        
        login_btn = ttk.Button(authTop, text="login", command=check_auth)
        login_btn.grid(row=3, column=0, sticky=tkinter.W+tkinter.E, columnspan=2)
    
    #
    # file menu methods
    #
    
    def openfile(self, filenames):
        chunks_to_load = ([self.annotation_name] if self.annotation_name else None)
        
        documents = []
        names = set()
        for filename in filenames:
            if filename.endswith(".sem.xml") or filename.endswith(".sem"):
                try:
                    docs = SEMCorpus.from_xml(filename, chunks_to_load=chunks_to_load, load_subtypes=True).documents
                    for doc in docs: # using reference annotations
                        for annotation_name in doc.annotations.keys():
                            doc.add_annotation(Annotation(annotation_name, reference=None, annotations=doc.annotation(annotation_name).get_reference_annotations()))
                    #documents.extend(docs)
                    for doc in [doc for doc in docs if doc.name not in names]:
                        documents.append(doc)
                        names.add(doc.name)
                except:
                    doc = Document.from_xml(filename, chunks_to_load=chunks_to_load, load_subtypes=True)
                    if doc.name not in names:
                        names.add(doc.name)
                        documents.append(doc)
                        for annotation_name in documents[-1].annotations.keys():
                            documents[-1].add_annotation(Annotation(annotation_name, reference=None, annotations=documents[-1].annotation(annotation_name).get_reference_annotations()))
            else:
                doc = sem.importers.load(filename, encoding="utf-8", tagset_name=self.annotation_name)
                if doc.name not in names:
                    documents.append(doc)
                    names.add(doc.name)
        
        if documents == []: return
        
        added = False
        for document in documents:
            tmp = self.add_document(document)
            added = added or tmp
        if not added:
            return
        
        self.load_document()
        
        self.train_btn.configure(state=tkinter.NORMAL)
        self.file_menu.entryconfig("Save to...", state=tkinter.NORMAL)
        self.file_menu.entryconfig("Save as...", state=tkinter.NORMAL)
        if self.adder is not None:
            self.adder.current_hierarchy_level = 0
            self.update_level()
    
    def openfile_gui(self, event=None):
        filenames = tkinter.filedialog.askopenfilenames(filetypes=[("SEM readable files", (".txt", ".sem.xml", ".sem", ".ann")), ("text files", ".txt"), ("BRAT files", (".txt", ".ann")), ("SEM XML files", ("*.sem.xml", ".sem")), ("All files", ".*")])
        if filenames == []: return
        self.openfile(filenames)
    
    def openurl(self, event=None):
        import urllib
        toplevel = tkinter.Toplevel()
        
        self.url = tkinter.StringVar()
        
        def cancel(event=None):
            self.url.set("")
            toplevel.destroy()
        def ok(event=None):
            document = sem.importers.from_url(self.url.get(), wikinews_format=bool(self.wikinews_format.get()), strip_html=True)
            if document is None: return
        
            added = self.add_document(document)
            if not added: return
            
            self.load_document()
            
            self.train_btn.configure(state=tkinter.NORMAL)
            self.file_menu.entryconfig("Save to...", state=tkinter.NORMAL)
            self.file_menu.entryconfig("Save as...", state=tkinter.NORMAL)
            cancel()
        
        label1 = tkinter.Label(toplevel, text="enter url:")
        label1.pack()
        
        text = ttk.Entry(toplevel, textvariable=self.url)
        text.pack()
        text.focus_set()
        
        c = ttk.Checkbutton(toplevel, text="Use Wikinews format", variable=self.wikinews_format)
        c.pack()
        
        toolbar = ttk.Frame(toplevel)
        toolbar.pack(side="top", fill="x")
        ok_btn = ttk.Button(toolbar, text="OK", command=ok)
        ok_btn.pack(side="left")
        cancel_btn = ttk.Button(toolbar, text="cancel", command=cancel)
        cancel_btn.pack(side="left")
        toplevel.bind('<Return>', ok)
        toplevel.bind('<Escape>', cancel)
        
        toolbar.pack()
    
    def add_tag(self, value, start, end):
        if type(start) == int:
            start_pos = self.charindex2position(start)
        else:
            start_pos = start
        if type(end) == int:
            end_pos = self.charindex2position(end)
        else:
            end_pos = end
        
        pos = (start, end)
        self.position2annots[pos] = self.position2annots.get(pos, set())
        
        if value not in self.position2annots[pos]:
            self.text.tag_add(value, start_pos, end_pos)
            self.position2annots[pos].add(value)
            self.doc_is_modified = True
    
    def save(self, event=None):
        filename = tkinter.filedialog.asksaveasfilename(defaultextension=".sem.xml")
        if filename == u"": return
        
        self.unselect()
        if self.doc_is_modified:
            update_annotations(self.doc, self.annotation_name, self.current_annotations.annotations)
        
        corpus = SEMCorpus(documents=self.corpus_documents)
        with codecs.open(filename, "w", "utf-8") as O:
            corpus.write(O)
    
    def save_as_format(self, output_directory, fmt):
        if not output_directory: return
        
        if self.doc_is_modified:
            update_annotations(self.doc, self.annotation_name, self.current_annotations.annotations)
        
        corpus = SEMCorpus(documents=self.corpus_documents)
        exporter = sem.exporters.get_exporter(fmt)()
        couples = {"ner":self.annotation_name}
        for document in corpus:
            name = os.path.basename(document.name).replace(":", "")
            out_path = os.path.join(output_directory, "{0}.{1}".format(os.path.splitext(name)[0], exporter.extension()))
            if fmt == "brat":
                if not name.endswith(".txt"):
                    name += ".txt"
                with codecs.open(os.path.join(output_directory, name), "w", "utf-8") as O:
                    O.write(document.content)
            exporter.document_to_file(document, couples, out_path, encoding="utf-8")
    
    def save_brat(self, event=None):
        output_directory = tkinter.filedialog.askdirectory(initialdir=sem.SEM_DATA_DIR)
        self.save_as_format(output_directory, "brat")
    
    def save_gate(self, event=None):
        output_directory = tkinter.filedialog.askdirectory(initialdir=sem.SEM_DATA_DIR)
        self.save_as_format(output_directory, "gate")
    
    def save_tei_analec(self, event=None):
        output_directory = tkinter.filedialog.askdirectory(initialdir=sem.SEM_DATA_DIR)
        self.save_as_format(output_directory, "tei_analec")
    
    def save_tei_reden(self, event=None):
        output_directory = tkinter.filedialog.askdirectory(initialdir=sem.SEM_DATA_DIR)
        self.save_as_format(output_directory, "tei_reden")
    
    def save_json(self, event=None):
        output_directory = tkinter.filedialog.askdirectory(initialdir=sem.SEM_DATA_DIR)
        self.save_as_format(output_directory, "jason")
    
    #
    # Edit menu methods
    #
    
    def preferences(self, event=None):
        preferenceTop = tkinter.Toplevel()
        preferenceTop.focus_set()
        
        notebook = ttk.Notebook(preferenceTop)
        
        frame1 = ttk.Frame(notebook)
        notebook.add(frame1, text='general')
        frame2 = ttk.Frame(notebook)
        notebook.add(frame2, text='shortcuts')

        c = ttk.Checkbutton(frame1, text="Match whole word when broadcasting annotation", variable=self._whole_word)
        c.pack()
        
        shortcuts_vars = []
        shortcuts_gui = []
        cur_row = 0
        j = -1
        frame_list = []
        frame_list.append(ttk.LabelFrame(frame2, text="common shortcuts"))
        frame_list[-1].pack(fill="both", expand="yes")
        for i, shortcut in enumerate(self.shortcuts):
            j += 1
            key, cmd, bindings = shortcut
            name, command = cmd
            shortcuts_vars.append(tkinter.StringVar(frame_list[-1], value=key))
            tkinter.Label(frame_list[-1], text=name).grid(row=cur_row, column=0, sticky=tkinter.W)
            entry = tkinter.Entry(frame_list[-1], textvariable=shortcuts_vars[j])
            entry.grid(row=cur_row, column=1)
            cur_row += 1
        notebook.pack()
    
    #
    # ? menu methods
    #
    
    def about_sem(self, event=None):
        options = {"background":"white"}
        aboutTop = tkinter.Toplevel(**options)
        aboutTop.title("About SEM")
        aboutTop.focus_set()
        
        two_cols = []
        two_cols.append(("author:", "Yoann Dupont"))
        two_cols.append(("mail:", "yoa.dupont@gmail.com"))
        two_cols.append(("website:", "http://www.lattice.cnrs.fr/sites/itellier/SEM.html"))
        two_cols.append(("github:", "https://github.com/YoannDupont/SEM"))
        two_cols.append(("online app:", "apps.lattice.cnrs.fr/sem"))
        
        x = 0
        label = ttk.Label(aboutTop, text=sem.full_name(), **options)
        label.grid(row=x, column=0)
        x += 1
        ttk.Label(aboutTop, text="", **options).grid(row=x, column=0)
        x += 1
        ttk.Label(aboutTop, text="", **options).grid(row=x, column=0)
        x += 1
        for key, val in two_cols:
            label = ttk.Label(aboutTop, text=key, **options)
            label.grid(row=x, column=0, sticky="w")
            label = ttk.Label(aboutTop, text=val, **options)
            label.grid(row=x, column=1, sticky="w")
            x += 1
            ttk.Label(aboutTop, text="", **options).grid(row=x, column=0)
            x += 1
    
    #
    # global methods
    #
    
    def train(self, event=None):
        if self.doc_is_modified:
            update_annotations(self.doc, self.annotation_name, self.current_annotations.annotations)
        
        train_interface = SEMTkTrainInterface(self.corpus_documents)
    
    def handle_char(self, event):
        if self.adder is None:
            return
        if not self.adder.current_annotation:
            try:
                self.text.index("sel.first")
            except tkinter.TclError:
                return
        
        the_type = self.adder.type_from_letter(event.keysym)
        the_type = the_type or self.adder.type_from_letter(event.keysym.lower())
        if the_type is None:
            return
        if event.keysym.islower():
            fst = (self.charindex2position(self.adder.current_annotation.lb) if self.adder.current_annotation else self.text.index("sel.first"))
            lst = (self.charindex2position(self.adder.current_annotation.ub) if self.adder.current_annotation else self.text.index("sel.last"))
            self.wish_to_add = [self.adder.type_from_letter(event.keysym), fst, lst]
            self.add_annotation(event, remove_focus=False)
        else:
            if self.adder.current_annotation is not None:
                start = self.charindex2position(self.adder.current_annotation.lb)
                end = self.charindex2position(self.adder.current_annotation.ub)
            else:
                start, end = ("sel.first", "sel.last")
            try:
                for match in find_occurrences(self.text.get(start, end), self.doc.content, whole_word=self.whole_word):
                    cur_start, cur_end = self.charindex2position(match.start()), self.charindex2position(match.end())
                    if Tag(the_type, match.start(), match.end()) not in self.current_annotations:
                        self.wish_to_add = [the_type, cur_start, cur_end]
                        self.add_annotation(None, remove_focus=False)
            except tkinter.TclError:
                raise
            self.unselect()
    
    def add_annotation(self, event, remove_focus=True):
        cur_type = self.type_combos[self.adder.current_hierarchy_level].get()
        if cur_type.strip() != u"" and cur_type != self.SELECT_TYPE:
            first = "sel.first"
            last = "sel.last"
            value = cur_type.split()[0]
        elif self.wish_to_add is not None:
            value, first, last = self.wish_to_add
        else:
            return
        
        text_select = False
        try:
            text_select = True
            if first == "sel.first":
                first = self.text.index("sel.first")
            if last == "sel.last":
                last = self.text.index("sel.last")
            
        except tkinter.TclError: # no selection
            return
        
        self.doc_is_modified = True
        if self.adder.current_hierarchy_level == 0:
            pos = (self.position2charindex(first), self.position2charindex(last))
            greater = [annot for annot in self.current_annotations if annot.lb<=pos[0] and annot.ub>=pos[1] and value==annot.value]
            tag = Tag(value, pos[0], pos[1])
            tag.levels = [value]
            if tag not in self.current_annotations and len(greater)==0:
                self.text.tag_add(value, first, last)
                self.adder.current_annotation = tag
                index = 0
                for annot in self.current_annotations:
                    if annot.lb > tag.lb:
                        break
                    index += 1
                key = u"{}".format(tag) # TODO: PY2
                item = self.tree.insert(self.tree_ids[self.annotation_name], index, text=u'{0} "{1}" [{2}:{3}]'.format(value, self.doc.content[pos[0] : pos[1]], pos[0], pos[1]))
                self.treeitem2annot[item] = tag
                self.annot2treeitems[self.annotation_name][key] = item
                self.current_annotations.add(tag)
                item2 = self.tree.insert(self.tree_ids["history"], 0, text=u'{0} "{1}" [{2}:{3}]'.format(value, self.doc.content[pos[0] : pos[1]], pos[0], pos[1]))
                self.treeitem2annot[item2] = tag
                self.annot2treeitems["history"][key] = item2
                self.ner2history[item] = item2
                self.adder.current_annotation = tag
            
            self.text.tag_remove("BOLD",  "1.0", 'end')
            self.type_combos[0].current(0)
        else:
            lb = self.position2charindex(first)
            ub = self.position2charindex(last)
            if self.wish_to_add is not None:
                for annot in self.current_annotations:
                    if annot.levels == []:
                        annot.levels = annot.value.split(u".")
                    if annot.getLevel(0) == self.adder.current_annotation.getLevel(0) and annot.lb == lb and annot.ub == ub:
                        tree_item_str = self.locate_tree_item()
                        tree_item =  self.tree.item(tree_item_str)
                        if check_in_tagset(annot.getValue(), self.tagset):
                            annot.setLevel(self.adder.current_hierarchy_level, self.wish_to_add[0])
                            new_text = u'{0} "{1}" [{2}:{3}]'.format(annot.getValue(), self.doc.content[annot.lb : annot.ub], lb, ub)
                            self.tree.item(tree_item_str, text=new_text)
                            prev_item = self.ner2history.get(tree_item_str)
                            if prev_item:
                                self.tree.delete(prev_item)
                                del self.treeitem2annot[prev_item]
                            new_item = self.tree.insert(self.tree_ids["history"], 0, text=new_text)
                            self.ner2history[tree_item_str] = new_item
                            self.treeitem2annot[new_item] = self.treeitem2annot[tree_item_str]
                            self.annot2treeitems["history"][u"{}".format(Tag(annot.getLevel(0), lb, ub))] = new_item # TODO: PY2
        if remove_focus:
            self.wish_to_add = None
            self.adder.current_annotation = None
            self.adder.current_hierarchy_level = 0
            self.update_level()
        else:
            self.text.tag_add("BOLD", first, last)
    
    def click(self, event):
        if self.doc is None or self.adder is None:
            return
        
        self.text.tag_remove("BOLD",  "1.0", 'end')
        prev_selection = self.adder.current_annotation
        self.adder.current_annotation = None
        self.wish_to_add = None
        index = event.widget.index("@{0},{1}".format(event.x, event.y))
        names = list(self.text.tag_names(index))
        charindex = self.position2charindex(index)
        try:
            names.remove("sel")
        except ValueError:
            pass
        
        annotations = [annotation for annotation in self.current_annotations if annotation.lb <= charindex and charindex <= annotation.ub]
        
        if annotations != self.annotations:
            self.annotations = annotations
            self.annotations_tick = -1
        self.annotations_tick += 1
        if self.annotations_tick >= len(self.annotations):
            self.annotations_tick = 0
        if len(self.annotations) > 0:
            curr_annot = self.annotations[self.annotations_tick]
            ci2p = self.charindex2position
            self.text.tag_add("BOLD", ci2p(curr_annot.lb), ci2p(curr_annot.ub))
            self.text.tag_remove(curr_annot.value, ci2p(curr_annot.lb), ci2p(curr_annot.ub))
            self.text.tag_add(curr_annot.value, ci2p(curr_annot.lb), ci2p(curr_annot.ub))
            self.adder.current_annotation = curr_annot
        
        tree_item = self.locate_tree_item()
        if tree_item is not None:
            self.tree.selection_set(tree_item)
            self.tree.focus(tree_item)
            self.select_from_tree()
            self.tree.see(tree_item)
        else:
            self.unselect()
        if len(annotations) == 0 or prev_selection != self.adder.current_annotation:
            self.adder.current_hierarchy_level = 0
            self.update_level()
    
    def locate_tree_item(self):
        if self.adder.current_annotation is None:
            return None
        if self.wish_to_add:
            lb = self.position2charindex(self.wish_to_add[1])
            ub = self.position2charindex(self.wish_to_add[2])
        else:
            lb = self.adder.current_annotation.lb
            ub = self.adder.current_annotation.ub
        ner_root = self.tree.get_children()[0]
        id = None
        value = self.adder.current_annotation.getLevel(0)
        bounds = "[{}:{}]".format(lb, ub)
        for child in self.tree.get_children(ner_root):
            text = self.tree.item(child)["text"]
            ok = text.startswith(value) and text.endswith(bounds)
            if ok:
                return child
        return None
    
    def select_from_tree(self, event=None):
        parent = self.tree.parent(self.tree.selection()[0])
        if not parent: return
        
        annot = self.treeitem2annot[self.tree.selection()[0]]
        lb_str = self.charindex2position(annot.lb)
        ub_str = self.charindex2position(annot.ub)
        
        self.text.tag_remove("BOLD", "1.0", 'end')
        self.text.tag_add("BOLD", lb_str, ub_str)
        self.adder.current_annotation = annot
        self.wish_to_add = None
        
        self.text.mark_set("insert", ub_str)
        self.text.see("insert")
    
    def unselect(self, event=None):
        self.text.tag_remove("BOLD",  "1.0", 'end')
        self.wish_to_add = None
        if self.adder:
            self.adder.current_annotation = None
            self.adder.current_hierarchy_level = 0
            self.update_level()
    
    def delete(self, event):
        self.text.tag_remove("BOLD",  "1.0", 'end')
        
        if self.adder.current_annotation is None: return
        
        value = self.adder.current_annotation.getValue()
        lb = self.adder.current_annotation.lb
        ub = self.adder.current_annotation.ub
        matching = [a for a in self.current_annotations if a.lb==lb and a.ub==ub and a.getValue()==value]
        greater = [a for a in self.current_annotations if a.lb<=lb and a.ub>=ub and a.getValue()==value and not a in matching]
        try:
            greater.remove(matching[0])
        except:
            pass
        for annotation in matching:
            if len(greater) == 0:
                self.text.tag_remove(self.adder.current_annotation.getLevel(0), self.charindex2position(annotation.lb), self.charindex2position(annotation.ub))
            tag = Tag(self.adder.current_annotation.getLevel(0), annotation.lb, annotation.ub)
            key = u"{}".format(tag) # TODO: PY2
            for v in self.annot2treeitems.values():
                item = v.get(key, None)
                if item is not None:
                    self.tree.delete(item)
                    if tag in self.current_annotations:
                        self.current_annotations.remove(self.adder.current_annotation)
                    del v[key]
                    del self.treeitem2annot[item]
        
        self.current_annotations.remove(self.adder.current_annotation)
        self.adder.current_annotation = None
        self.adder.current_hierarchy_level = 0
        self.update_level()
        self.doc_is_modified = True
    
    def delete_all(self, event):
        if self.adder.current_annotation is not None:
            value = self.adder.current_annotation.value
            start = self.adder.current_annotation.lb
            end = self.adder.current_annotation.ub
            for occ in find_occurrences(self.doc.content[start:end], self.doc.content, whole_word=False):
                self.adder.current_annotation = Tag(value, occ.start(), occ.end())
                self.delete(event)
        self.adder.current_annotation = None
        self.adder.current_hierarchy_level = 0
        self.update_level()
        self.text.tag_remove("BOLD",  "1.0", 'end')
        self.doc_is_modified = True
    
    def position2charindex(self, position):
        line, index = [int(e) for e in position.split(".")]
        return sum(self.lines_lengths[:line]) + index
    
    def charindex2position(self, charindex):
        lengths = self.lines_lengths
        cur = 0
        line = 1
        while cur+lengths[line] <= charindex:
            cur += lengths[line]
            line += 1
        offset = charindex - cur
        return u"{0}.{1}".format(line, offset)
    
    def tab(self, event=None):
        self.adder.up_one_level()
        self.update_level()
    
    def shift_tab(self, event=None):
        self.adder.down_one_level()
        self.update_level()
    
    def update_level(self):
        for i in range(self.adder.max_depth()):
            if i != self.adder.current_hierarchy_level:
                self.type_combos[i].configure(state=tkinter.DISABLED)
            else:
                levels = (self.adder.current_annotation.levels if self.adder.current_annotation is not None else [])
                subtrie = self.adder.shortcut_trie.goto(levels)
                keys = sorted([key for key in subtrie if key != NUL])
                for j in range(len(keys)):
                    shortcut = subtrie[keys[j]][NUL]
                    keys[j] += " ({0} or Shift+{0})".format(shortcut)
                self.type_combos[i]["values"] = [self.SELECT_TYPE] + keys
                self.type_combos[i].configure(state="readonly")
    
    def add_document(self, document):
        found = self.doc is not None and any([document.name == doc.name for doc in self.corpus_documents])
        if found:
            id = self.corpus_id2doc[self.doc.name]
            self.corpus_tree.selection_set(id)
            self.corpus_tree.focus(id)
            self.corpus_tree.see(id)
        else:
            id = self.corpus_tree.insert("", len(self.corpus_tree.get_children()), text=document.name)
            self.corpus_id2doc[id] = document
            self.corpus_doc2id[document.name] = id
            self.corpus_documents.append(document)
            self.corpus_tree.selection_set(id)
            self.corpus_tree.focus(id)
            self.corpus_tree.see(id)
        return not found
    
    def load_document(self, event=None, same_doc=False):
        try:
            selection = self.corpus_tree.selection()[0]
        except IndexError:
            return
        
        document = self.corpus_id2doc[selection]
        if self.doc is None or (document.name != self.doc.name or same_doc):
            if self.doc is not None and self.doc_is_modified:
                update_annotations(self.doc, self.annotation_name, self.current_annotations.annotations)
            
            self.doc = document
            
            previous_tree = self.tree_ids.get(self.annotation_name, None)
            if previous_tree:
                self.tree.delete(previous_tree)
            previous_tree = self.tree_ids.get("history", None)
            if previous_tree:
                self.tree.delete(previous_tree)
            
            if self.annotation_name is not None:
                self.tree_ids[self.annotation_name] = self.tree.insert("", len(self.tree_ids)+1, text=self.annotation_name)
                self.tree_ids["history"] = self.tree.insert("", len(self.tree_ids)+1, text="history")
                self.annot2treeitems[self.annotation_name] = {}
            self.annot2treeitems["history"] = {}
            self.treeitem2annot = {}
            self.position2annots = {}
            self.current_annotations = Annotation("CurrentAnnotations")
            if self.adder is not None:
                self.adder.current_annotation = None
            self.wish_to_add = None
            self.lines_lengths = [0] + [len(line)+1 for line in self.doc.content.split(u"\n")]
            
            self.text.configure(state="normal")
            for tag_name in self.text.tag_names():
                self.text.tag_remove(tag_name, "1.0", "end")
            self.text.delete("1.0", "end")
            self.text.insert("end", self.doc.content)
            self.text.tag_remove("BOLD",  "1.0", 'end')
            self.text.configure(state="disabled")
            
            if self.doc.annotation(self.annotation_name):
                annots = self.doc.annotation(self.annotation_name).get_reference_annotations()
                for nth_annot, annot in enumerate(annots):
                    annot.levels = annot.value.split(u".")
                    self.add_tag(annot.levels[0], annot.lb, annot.ub)
                    item = self.tree.insert(self.tree_ids[self.annotation_name], len(self.annot2treeitems[self.annotation_name])+1, text=u'{0} "{1}" [{2}:{3}]'.format(annot.value, self.doc.content[annot.lb : annot.ub], annot.lb, annot.ub))
                    self.annot2treeitems[self.annotation_name][u"{}".format(annot)] = item # TODO: PY2
                    annot.ids[self.annotation_name] = item
                    self.treeitem2annot[item] = annot
                    self.current_annotations.add(annot)
                    if self.adder.shortcut_trie.goto(annot.levels[0]) is None:
                        separator = find_potential_separator(annot.value)
                        if separator is not None:
                            splitted = annot.value.split(separator)
                            for depth, type_to_add in enumerate(splitted,0):
                                self.doc.annotation(self.annotation_name)[nth_annot].setLevel(depth, type_to_add)
                        else:
                            self.doc.annotation(self.annotation_name)[nth_annot].setLevel(0, annot.value)
        self.doc_is_modified = False
    
    def load_tagset(self, filename):
        if self.doc and self.doc_is_modified:
            update_annotations(self.doc, self.annotation_name, self.current_annotations.annotations)
        
        tagset_name = os.path.splitext(os.path.basename(filename))[0]
        tagset = []
        with codecs.open(filename, "rU", "utf-8") as I:
            for line in I:
                tagset.append(line.strip())
        tagset = [tag.split(u"#",1)[0] for tag in tagset]
        tagset = [tag for tag in tagset if tag != u""]
        
        self.spare_colors = self.SPARE_COLORS_DEFAULT[:]
        self.annotation_name = tagset_name
        self.tagset = set(tagset)
        
        for combo in self.type_combos:
            combo.destroy()
        self.type_combos = []
        for add_type_lbl in self.add_type_lbls:
            add_type_lbl.destroy()
        self.add_type_lbls = [ttk.Label(self.toolbar, text="add type:")]
        self.add_type_lbls[0].pack(side="left")
        
        for child in self.tree.get_children():
            self.tree.delete(child)
        self.tree_ids[self.annotation_name] = self.tree.insert("", len(self.tree_ids)+1, text=self.annotation_name)
        self.tree_ids["history"] = self.tree.insert("", len(self.tree_ids)+1, text="history")
        self.annot2treeitems[self.annotation_name] = {}
        
        self.type_combos.append(ttk.Combobox(self.toolbar))
        self.type_combos[0]["values"] = [self.SELECT_TYPE]
        self.type_combos[0].bind("<<ComboboxSelected>>", self.add_annotation)
        self.type_combos[0].pack(side="left")
        
        self.adder = Adder2.from_tagset(tagset)
        for depth in range(self.adder.max_depth()):
            ## label
            self.add_type_lbls.append(ttk.Label(self.toolbar, text="add {0}type:".format("sub"*(depth))))
            self.add_type_lbls[depth].pack(side="left")
            # combobox
            self.type_combos.append(ttk.Combobox(self.toolbar))
            self.type_combos[depth]["values"] = [self.SELECT_TYPE]
            self.type_combos[depth].bind("<<ComboboxSelected>>", self.add_annotation)
            self.type_combos[depth].pack(side="left")
            for tag in sorted(set([t[depth] for t in self.adder.levels if len(t) > depth])):
                if len(self.type_combos) > 0:
                    self.type_combos[depth]["values"] = list(self.type_combos[depth]["values"]) + [tag]
                if depth == 0:
                    if len(self.spare_colors) > 0:
                        self.color = self.spare_colors.pop()
                    else:
                        self.color = random_color()
                    self.text.tag_configure(tag, **self.color)
        self.update_level()
        self.doc = None
        self.load_document()
    
    def load_tagset_gui(self, event=None):
        filename = tkinter.filedialog.askopenfilename(filetypes=[("text files", ".txt"), ("All files", ".*")], initialdir=os.path.join(sem.SEM_DATA_DIR, "resources", "tagsets"))
        
        if len(filename) == 0: return
        
        self.load_tagset(filename)
    
    def find_in_text(self, event=None):
        self.search.find_in_text(event=event)
    
    def load_pipeline(self, event=None):
        top = tkinter.Toplevel()
        master_selector = SemTkMasterSelector(top, os.path.join(sem.SEM_DATA_DIR, "resources"))
        lang_selector = SemTkLangSelector(top, os.path.join(sem.SEM_DATA_DIR, "resources"))
        lang_selector.master_selector = master_selector
        vars_cur_row = 0
        vars_cur_row, _ = lang_selector.grid(row=vars_cur_row, column=0)
        vars_cur_row, _ = master_selector.grid(row=vars_cur_row, column=0)
        
        def cancel(event=None):
            if self.pipeline is not None:
                self.tag_document_btn.configure(state=tkinter.NORMAL)
            top.destroy()
        def ok(event=None):
            path = master_selector.workflow()
            pipeline, _, _, _ = sem.modules.tagger.load_master(path)
            self.pipeline = pipeline
            cancel()
        
        ok_btn = ttk.Button(top, text="load workflow", command=ok)
        ok_btn.grid(row=vars_cur_row, column=0)
        cancel_btn = ttk.Button(top, text="cancel", command=cancel)
        cancel_btn.grid(row=vars_cur_row, column=1)
    
    def tag_document(self, event=None):
        if self.pipeline is None:
            return
        
        self.pipeline.process_document(self.doc)
        self.doc_is_modified = True
        for key in self.doc.annotations:
            annotation = self.doc.annotation(key)
            self.doc.add_annotation(Annotation(annotation.name, annotations=annotation.get_reference_annotations()))
        self.current_annotations = self.doc.annotation(self.annotation_name)
        self.load_document(same_doc=True)

_subparsers = sem.argument_subparsers

parser = _subparsers.add_parser(os.path.splitext(os.path.basename(__file__))[0], description="An annotation tool for SEM.")

parser.add_argument("-d", "--documents", nargs="*",
                    help="Documents to load at startup.")
parser.add_argument("-t", "--tagset",
                    help="The tagser to load at startup.")
parser.add_argument("-l", "--log", dest="log_level", choices=("DEBUG","INFO","WARNING","ERROR","CRITICAL"), default="WARNING",
                    help="Increase log level (default: %(default)s)")

def main(args):
    root = tkinter.Tk()
    root.title("SEM")
    AnnotationTool(root, args.log_level, documents=args.documents, tagset=args.tagset).pack(expand=1, fill="both")
    root.mainloop()
