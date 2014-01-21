# Some small utility tools

## diffconflicts

Workflow:

1.    Save your changes to the LCONFL temporary file (the left window on the
      first tab; also the only file that isn't read-only).
2.    The LOCAL, BASE, and REMOTE versions of the file are available in the
      second tabpage if you want to look at them.
3.    When vimdiff exits cleanly, the file containing the conflict markers
      will be updated with the contents of your LCONFL file edits.

NOTE: Use :cq to abort the merge and exit Vim with an error code.

Add this mergetool to your ~/.gitconfig (you can substitute vim for gvim):

git config --global merge.tool diffconflicts
git config --global mergetool.diffconflicts.cmd 'diffconflicts vim $BASE $LOCAL $REMOTE $MERGED'
git config --global mergetool.diffconflicts.trustExitCode true
git config --global mergetool.diffconflicts.keepBackup false
