import beartype, typing
from beartype import beartype as bt
print("beartype", beartype.__version__)
@typing.runtime_checkable
class RB(typing.Protocol):
    def grab(self) -> bool: ...
class P(typing.Protocol):
    def grab(self) -> bool: ...
class Good:
    def grab(self) -> bool: return True
class Bad: pass
@bt
def f(b: RB) -> bool: return b.grab()
print("good ok:", f(Good()))
try: f(Bad()); print("bad accepted")
except Exception as e: print("bad rejected:", type(e).__name__)
try:
    @bt
    def g(b: P) -> bool: return True
    print("plain protocol decorated OK; call:", end=" ")
    try: print(g(Bad()))
    except Exception as e: print(type(e).__name__)
except Exception as e: print("plain protocol decoration failed:", type(e).__name__)
